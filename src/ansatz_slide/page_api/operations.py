"""页面级快照、预览和可恢复的源文件发布。

本 API 将编辑会话绑定到页面与源文件哈希，校验并预览候选稿后，只发布目标
页面或清单顺序变更。令牌用于发现过期输入，但不能阻止外部写入，因此发布
前后还会复查哈希，并保留备份以便回滚。
"""

import copy
import json
import re
import uuid
from pathlib import Path

from ..file_transactions import preserving_replace
from ..project import (
    atomic_write,
    image_objects,
    parse_document,
    source_bytes,
)
from ..validation import safe_path, validate_project
from .checks import preview, response
from .state import (
    json_bytes,
    lock,
    page_fingerprint,
    page_token,
    session_path,
    session_write,
    sha,
    snapshot,
    unchanged,
)


def check_page(project, number, session, width=1600):
    """创建绑定源版本的页面会话及其初始审阅证据。"""
    session = session_path(session)
    if width < 400 or width > 8000:
        raise ValueError("Width must be 400..8000 pixels")
    with lock(session / ".session.lock"):
        snap = snapshot(project)
        if number < 1 or number > len(snap["pages"]):
            raise ValueError("Page out of range")
        if any(Path(p).is_relative_to(session) for p in snap["tracked"]):
            raise ValueError(
                "Session directory must not contain original source files or assets"
            )
        state_path = session / "session.json"
        if state_path.exists():
            old = json.loads(state_path.read_text())
            if old["project"] != str(snap["manifestPath"]) or old["page"] != number:
                raise ValueError(
                    "Session is pinned to another page/project; use another session directory"
                )
            draft = session / "page.page.yaml"
            if draft.is_file() and sha(draft.read_bytes()) != old.get("draftHash"):
                raise ValueError(
                    "Session has an unapplied draft; use page edit or a new session"
                )
        rendered = preview(snap, number, snap["pages"][number - 1], session, width)
        state = {
            "format": 1,
            "project": str(snap["manifestPath"]),
            "page": number,
            "token": page_token(snap, number),
            "width": width,
            "draftHash": sha(json_bytes(snap["pages"][number - 1])),
            **rendered,
        }
        session_write(session, "page.page.yaml", json_bytes(snap["pages"][number - 1]))
        session_write(session, "session.json", json_bytes(state))
    return response(session, state, snap)


def edit_page(session, token, content=None, *, element_id=None, changes=None):
    """重新校验并渲染后，应用一个页面候选稿。

    源文件发布前先更新会话草稿；若后续复核失败，源文件事务会回滚，草稿
    仍保留供检查或重试。
    """
    session = session_path(session)
    with lock(session / ".session.lock"):
        state_path = session / "session.json"
        state = json.loads(state_path.read_text())
        if state.get("format") != 1:
            raise ValueError("Unsupported page session")
        project = Path(state["project"])
        with lock(project.parent / ".ansatz-page-edit.lock"):
            snap = snapshot(project)
            number = state["page"]
            if number < 1 or number > len(snap["pages"]):
                raise ValueError("Selected page no longer exists")
            if token != state["token"] or token != page_token(snap, number):
                raise ValueError("Stale page input; run page check again")
            if element_id is not None:
                if content is not None:
                    raise ValueError("Element patch cannot also replace the page")
                draft = session / "page.page.yaml"
                if draft.is_file() and sha(draft.read_bytes()) != state.get(
                    "draftHash"
                ):
                    raise ValueError(
                        "Session has an unapplied draft; apply it or check in a new session before patching"
                    )
                candidate = patch_element(
                    snap["pages"][number - 1], element_id, changes
                )
            else:
                candidate_path = (
                    Path(content).resolve() if content else session / "page.page.yaml"
                )
                candidate = parse_document(
                    candidate_path.read_text(encoding="utf-8"), str(candidate_path)
                )
            rendered = preview(snap, number, candidate, session, state["width"])
            from ..occupancy import require_pass

            require_pass(rendered["geometry"])
            path = snap["paths"][number - 1]
            draft_data = json_bytes(candidate)
            new_data = source_bytes(draft_data)
            session_write(session, "page.page.yaml", draft_data)
            if not unchanged(snap["tracked"]) or not unchanged(
                rendered["_assetHashes"]
            ):
                raise RuntimeError(
                    "Concurrent source or asset edit; run page check again"
                )
            publication = preserving_replace(path, new_data, snap["tracked"][str(path)])
            try:
                updated = snapshot(project)
                if (
                    updated["tracked"].get(str(path)) != sha(new_data)
                    or not unchanged(
                        {p: h for p, h in snap["tracked"].items() if p != str(path)}
                    )
                    or not unchanged(rendered["_assetHashes"])
                ):
                    raise RuntimeError("Source changed concurrently; edit not accepted")
                new_state = {
                    **state,
                    **rendered,
                    "token": page_token(updated, number),
                    "draftHash": sha(draft_data),
                }
                session_write(session, "session.json", json_bytes(new_state))
            except Exception:
                publication.rollback()
                raise
    return {
        **response(session, new_state, updated),
        "changedPages": [number],
        "nonTargetSources": "unchanged",
        "recoverySource": str(publication.backup),
        "effect": "Updated one page source; full-deck PPTX not overwritten. The returned image is the new single-page preview.",
    }


def reshape_pages(session, token, contents, next_session=None, next_token=None):
    """Split one checked page, or merge two separately checked adjacent pages.

    New sources are staged first; recoverable manifest publication applies the
    new order. Retired sources remain on disk for recovery, outside that order.
    """
    session = session_path(session)
    with lock(session / ".session.lock"):
        state = json.loads((session / "session.json").read_text())
        project = Path(state["project"])
        with lock(project.parent / ".ansatz-page-edit.lock"):
            snap = snapshot(project)
            number = state["page"]
            if token != state["token"] or token != page_token(snap, number):
                raise ValueError("Stale page input; run page check again")
            count = 1
            if next_session is not None:
                other = json.loads(
                    (session_path(next_session) / "session.json").read_text()
                )
                if other["project"] != str(project) or other["page"] != number + 1:
                    raise ValueError(
                        "Merge requires the separately checked immediately following page of this project"
                    )
                if next_token != other["token"] or next_token != page_token(
                    snap, number + 1
                ):
                    raise ValueError("Stale adjacent page input; run page check again")
                count = 2
            if (count == 1 and len(contents) < 2) or (
                count == 2 and len(contents) != 1
            ):
                raise ValueError(
                    "Split requires at least two page objects; merge requires exactly one"
                )
            candidates = [
                parse_document(Path(p).read_text(encoding="utf-8"), str(p))
                for p in contents
            ]
            if any(not isinstance(p, dict) or "pages" in p for p in candidates):
                raise ValueError(
                    "Each content file must contain exactly one page object"
                )
            names = [f"page-{uuid.uuid4().hex}.page.yaml" for _ in candidates]
            manifest = copy.deepcopy(snap["manifest"])
            manifest["pages"][number - 1 : number - 1 + count] = names
            pages = (
                snap["pages"][: number - 1]
                + candidates
                + snap["pages"][number - 1 + count :]
            )
            validate_project(manifest, pages, snap["root"], check_files=False)
            from ..occupancy import require_pages

            require_pages(manifest["size"], pages)
            candidate_assets = {}
            for image in image_objects({"pages": candidates}):
                if not re.match(r"(?i)^(data:|https?://)", image["src"]):
                    asset = safe_path(snap["root"], image["src"], "image")
                    candidate_assets[str(asset)] = sha(asset.read_bytes())
            rendered = [
                preview(snap, number, p, session, state["width"]) for p in candidates
            ]
            from ..occupancy import require_pass

            for r in rendered:
                require_pass(r["geometry"])
            if not unchanged(snap["tracked"]) or not unchanged(candidate_assets):
                raise RuntimeError(
                    "Concurrent source or asset edit; run page check again"
                )
            publication = publish_order(
                snap, manifest, dict(zip(names, candidates)), candidate_assets
            )
            return {
                "operation": "merge" if count == 2 else "split",
                "replacedPages": list(range(number, number + count)),
                "pageCount": len(pages),
                "recoveryManifest": str(publication.backup),
                "textFit": [r["typography"] for r in rendered],
                "newPages": [
                    {
                        "page": number + i,
                        "sourcePage": str(snap["root"] / name),
                        "image": str(session / r["image"]),
                        "previewPptx": str(session / r["previewPptx"]),
                        "geometry": r["geometry"],
                    }
                    for i, (name, r) in enumerate(zip(names, rendered))
                ],
                "retiredSources": [
                    str(p) for p in snap["paths"][number - 1 : number - 1 + count]
                ],
                "effect": "Only this local span was replaced in the manifest order. Existing page files and assets remain unchanged; retired sources are retained. Full-deck PPTX is not overwritten.",
                "nextCommand": [
                    "ansatz-slide",
                    "page",
                    "check",
                    "--project",
                    str(project),
                    "--page",
                    str(number),
                    "--session",
                    str(session.parent / f"check-{uuid.uuid4().hex[:8]}"),
                ],
            }


def patch_element(page, element_id, changes):
    """Recursively merge fields into exactly one existing element; arrays replace."""
    if not isinstance(changes, dict) or not changes:
        raise ValueError("Changes must be a non-empty object of element fields")
    if {"elementId", "elementType"} & changes.keys():
        raise ValueError("Patch cannot change element identity or type")
    candidate = copy.deepcopy(page)
    matches = [
        e for e in candidate.get("elements", []) if e.get("elementId") == element_id
    ]
    if len(matches) != 1:
        raise ValueError("Element ID must identify exactly one element on this page")

    def merge(target, fields):
        for key, value in fields.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = copy.deepcopy(value)

    merge(matches[0], changes)
    return candidate


def checked_state(session, token, snap):
    state = json.loads((session / "session.json").read_text())
    if state.get("format") != 1 or state["project"] != str(snap["manifestPath"]):
        raise ValueError("Session must belong to this project")
    number = state["page"]
    if (
        number < 1
        or number > len(snap["pages"])
        or token != state["token"]
        or token != page_token(snap, number)
    ):
        raise ValueError("Stale page input; run page check again")
    return state


def publish_order(snap, manifest, new_sources=None, assets=None):
    """发布新增源文件及有序清单，同时保留已有源文件。

    先创建新页面文件，再由清单切换可见顺序。已有或退役页面文件不会删除；
    替换后的检查失败时，可使用保留的清单备份恢复。
    """
    new_sources = new_sources or {}
    from ..occupancy import require_pages

    existing = dict(zip(snap["manifest"]["pages"], snap["pages"]))
    pages = [
        new_sources[name] if name in new_sources else existing[name]
        for name in manifest["pages"]
    ]
    require_pages(manifest["size"], pages)
    assets = assets or {}
    project = snap["manifestPath"]
    created = []
    publication = None
    try:
        if not unchanged(snap["tracked"]) or not unchanged(assets):
            raise RuntimeError("Concurrent source or asset edit; run page check again")
        for name, page in new_sources.items():
            path = snap["root"] / name
            atomic_write(path, source_bytes(json_bytes(page)), force=False)
            created.append(path)
        if not unchanged(snap["tracked"]) or not unchanged(assets):
            raise RuntimeError("Concurrent source or asset edit; run page check again")
        publication = preserving_replace(
            project, source_bytes(json_bytes(manifest)), snap["tracked"][str(project)]
        )
        if not unchanged(assets) or not unchanged(
            {p: h for p, h in snap["tracked"].items() if p != str(project)}
        ):
            raise RuntimeError(
                "Concurrent source or asset edit during publication; retry page check"
            )
    except Exception:
        if publication is not None:
            publication.rollback()
        # Keep staged sources if an external manifest may have referenced them.
        # Unreferenced sources are recoverable and never destroy existing data.
        raise
    return publication


def change_order(
    session,
    token,
    operation,
    *,
    content=None,
    position="after",
    anchor_session=None,
    anchor_token=None,
    allow_duplicates=False,
):
    """Insert next to a checked page, move relative to a checked anchor, or remove."""
    if operation not in ("insert", "move", "remove"):
        raise ValueError("Unknown page order operation")
    if position not in ("before", "after"):
        raise ValueError("Position must be before or after")
    session = session_path(session)
    with lock(session / ".session.lock"):
        initial = json.loads((session / "session.json").read_text())
        project = Path(initial["project"])
        with lock(project.parent / ".ansatz-page-edit.lock"):
            snap = snapshot(project)
            state = checked_state(session, token, snap)
            number = state["page"]
            manifest = copy.deepcopy(snap["manifest"])
            order = manifest["pages"]
            pages = copy.deepcopy(snap["pages"])
            selected = order[number - 1]
            sources, assets, rendered = {}, {}, None
            if operation == "insert":
                if content is None:
                    raise ValueError("Insert requires one page content file")
                candidate = parse_document(
                    Path(content).read_text(encoding="utf-8"), str(content)
                )
                if not allow_duplicates and any(
                    page_fingerprint(candidate) == page_fingerprint(p)
                    for p in snap["pages"]
                ):
                    raise ValueError(
                        "Duplicate page content detected; insertion was not published. Use --allow-duplicates only for intentional repetition."
                    )
                for image in image_objects(candidate):
                    if not re.match(r"(?i)^(data:|https?://)", image["src"]):
                        asset = safe_path(snap["root"], image["src"], "image")
                        assets[str(asset)] = sha(asset.read_bytes())
                name = f"page-{uuid.uuid4().hex}.page.yaml"
                index = number if position == "after" else number - 1
                order.insert(index, name)
                pages.insert(index, candidate)
                sources[name] = candidate
                affected = index + 1
            elif operation == "remove":
                if len(order) == 1:
                    raise ValueError(
                        "Cannot remove the last page; projects require at least one page"
                    )
                order.pop(number - 1)
                pages.pop(number - 1)
                affected = min(number, len(order))
            else:
                if anchor_session is None:
                    raise ValueError("Move requires a checked anchor session")
                anchor = checked_state(session_path(anchor_session), anchor_token, snap)
                if anchor["page"] == number:
                    raise ValueError("Cannot move a page relative to itself")
                anchor_name = order[anchor["page"] - 1]
                moved = pages.pop(number - 1)
                order.pop(number - 1)
                index = order.index(anchor_name) + (position == "after")
                order.insert(index, selected)
                pages.insert(index, moved)
                affected = index + 1
            validate_project(manifest, pages, snap["root"], check_files=False)
            from ..occupancy import require_pages

            require_pages(manifest["size"], pages)
            if operation == "insert":
                rendered = preview(snap, number, candidate, session, state["width"])
            publication = publish_order(snap, manifest, sources, assets)
            result = {
                "operation": operation,
                "pageCount": len(order),
                "page": affected,
                "recoveryManifest": str(publication.backup),
                "sourcePage": str(snap["root"] / order[affected - 1]),
                "existingSources": "unchanged; removed sources retained on disk",
                "effect": "Updated manifest order; full-deck PPTX is not overwritten.",
                "nextCommand": [
                    "ansatz-slide",
                    "page",
                    "check",
                    "--project",
                    str(project),
                    "--page",
                    str(affected),
                    "--session",
                    str(session.parent / f"check-{uuid.uuid4().hex[:8]}"),
                ],
            }
            if rendered:
                result.update(
                    image=str(session / rendered["image"]),
                    previewPptx=str(session / rendered["previewPptx"]),
                    geometry=rendered["geometry"],
                    typography=rendered["typography"],
                )
            if operation == "move":
                result["fromPage"] = number
            if operation == "remove":
                result.update(
                    removedPage=number, removedSource=str(snap["root"] / selected)
                )
            return result
