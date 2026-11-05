"""绑定修订版本的页面工作对象：候选稿、证据和下一步操作。

每次操作都会在同一谱系中新建工作目录，并明确记录当前 head。源哈希过期会
形成冲突；候选稿须通过结构、源稿预检、几何及所需预览后才发布。保留的候选
稿和诊断信息用于恢复；resume 不会隐式 rebase 或应用候选稿。
"""

import copy
import json
from pathlib import Path

from .. import narrative as outline
from .. import page_api as api
from ..occupancy import check_geometry, require_pass, write_geometry
from ..output import attach as attach_gates
from ..project import atomic_write, manifest_paths, parse_document, source_bytes
from ..validation import validate_project
from .processing import _process
from .state import (
    _conflict,
    _content_signature,
    _current,
    _layout_rejection,
    _new,
    _read,
    _root,
    _split_preserves_content,
)


def open_page(project, number, width=1600, *, render=True):
    if not 400 <= width <= 8000:
        raise ValueError("Width must be 400..8000")
    snap = api.snapshot(project)
    if not 1 <= number <= len(snap["pages"]):
        raise ValueError("Page out of range")
    root = _root(snap["root"])
    work = _new(root)
    record = {
        "format": 1,
        "project": str(snap["manifestPath"]),
        "page": number,
        "width": width,
        "sourcePath": str(snap["paths"][number - 1]),
        "baseToken": api.page_token(snap, number),
        "operation": {"kind": "edit"},
        "candidates": [snap["pages"][number - 1]],
    }
    return _process(work, record, snap, apply=False, render=render)


def update(
    work,
    content=None,
    element=None,
    changes=None,
    candidate=1,
    *,
    edits=None,
    layout=None,
    allow_duplicates=False,
):
    work, record = _read(work)
    with api.lock(work.parent / ".work.lock"):
        try:
            snap = _current(work, record)
        except Exception as exc:
            return _conflict(work, record, str(exc))
        record = copy.deepcopy(record)
        if allow_duplicates:
            if record["operation"]["kind"] != "insert":
                raise ValueError(
                    "--allow-duplicates only applies to a retained insertion"
                )
            record["operation"]["allowDuplicates"] = True
        if not 1 <= candidate <= len(record["candidates"]):
            raise ValueError("Candidate index out of range")
        if sum(value is not None for value in (content, element, edits)) > 1:
            raise ValueError("Choose full content, one element update, or edits")
        if layout is not None and (content is not None or element is not None):
            raise ValueError(
                "Layout can be combined with edits, not content or element"
            )
        original = record["candidates"][candidate - 1]
        if content is not None:
            record["candidates"][candidate - 1] = parse_document(
                Path(content).read_text(), str(content)
            )
        elif element is not None:
            record["candidates"][candidate - 1] = api.patch_element(
                record["candidates"][candidate - 1], element, changes
            )
        if edits is not None:
            if not isinstance(edits, list) or not edits:
                raise ValueError("Edits must be a nonempty list of {element, changes}")
            for edit in edits:
                if (
                    not isinstance(edit, dict)
                    or set(edit) != {"element", "changes"}
                    or not isinstance(edit["element"], str)
                    or not isinstance(edit["changes"], dict)
                ):
                    raise ValueError(
                        "Each edit needs exactly element (string) and changes (object)"
                    )
                record["candidates"][candidate - 1] = api.patch_element(
                    record["candidates"][candidate - 1],
                    edit["element"],
                    edit["changes"],
                )
        if layout is not None:
            from ..layout import apply_layout

            record["candidates"][candidate - 1] = apply_layout(
                record["candidates"][candidate - 1], layout
            )
        failures = record.get("geometryFailures", [])
        if candidate <= len(failures) and failures[candidate - 1] > 0:
            if _content_signature(original) != _content_signature(
                record["candidates"][candidate - 1]
            ):
                return _layout_rejection(
                    work,
                    "After geometry failure, only bounds/rotation and element ordering may change. Content, styles and elements are frozen; rejected input did not replace the retained candidate.",
                )
        return _process(_new(work.parent), record, snap, apply=True)


def change(
    work, kind, contents=(), other=None, position="after", *, allow_duplicates=False
):
    work, record = _read(work)
    with api.lock(work.parent / ".work.lock"):
        try:
            snap = _current(work, record)
        except Exception as exc:
            return _conflict(work, record, str(exc))
        pending = json.loads((work / "result.json").read_text())["status"] not in (
            "ready",
            "applied",
        )
        repair_split = (
            kind == "split"
            and record["operation"]["kind"] in ("edit", "create")
            and any(record.get("geometryFailures", []))
        )
        if pending and not repair_split:
            return attach_gates(
                {
                    **json.loads((work / "result.json").read_text()),
                    "issues": [
                        {
                            "kind": "pending",
                            "message": "Repair or reopen this pending candidate before changing page structure",
                        }
                    ],
                }
            )
        record = copy.deepcopy(record)
        creating = record["operation"]["kind"] == "create"
        originals = record["candidates"]
        record["operation"] = {
            "kind": "create" if creating else kind,
            "position": position,
            "other": str(other) if other else None,
            "allowDuplicates": allow_duplicates,
        }
        if kind in ("insert", "split", "merge"):
            expected = 2 if kind == "split" else 1
            if len(contents) < expected or (kind != "split" and len(contents) != 1):
                raise ValueError("Wrong candidate count")
            record["candidates"] = [
                parse_document(Path(p).read_text(), str(p)) for p in contents
            ]
        if repair_split and not _split_preserves_content(
            originals, record["candidates"]
        ):
            return _layout_rejection(
                work,
                "Repair split must redistribute existing elements and preserve their content/styles and notes; do not remove or rewrite content to pass geometry.",
            )
        record["geometryFailures"] = [0] * len(record["candidates"])
        return _process(_new(work.parent), record, snap, apply=True)


def create(project, settings, content, width=1600):
    root = api.session_path(project)
    root.mkdir(parents=True, exist_ok=True)
    if manifest_paths(root):
        raise ValueError("Project already has a manifest")
    if not isinstance(settings, dict) or "pages" in settings:
        raise ValueError("Settings contain version/size/theme/title, not page paths")
    record = {
        "format": 1,
        "project": str(root),
        "page": 1,
        "width": width,
        "settings": settings,
        "baseToken": None,
        "operation": {"kind": "create"},
        "candidates": [content],
    }
    work = _new(_root(root))
    return _process(work, record, None, apply=True)


def resume(token):
    """Resolve a stable lineage token without applying or rebasing a candidate."""
    token = api.session_path(token)
    root = token if (token / "head.json").is_file() else token.parent
    work = api.session_path(json.loads((root / "head.json").read_text())["work"])
    if work.parent != root:
        raise ValueError("Invalid work head")
    work, record = _read(work)
    try:
        _current(work, record)
    except Exception as exc:
        return _conflict(work, record, str(exc))
    return json.loads((work / "result.json").read_text())


def rebase(token, number=None):
    """Explicitly recover candidates after source changes; never publish here."""
    current = resume(token)
    work, record = _read(current["work"])
    with api.lock(work.parent / ".work.lock"):
        if json.loads((work.parent / "head.json").read_text())["work"] != str(work):
            raise ValueError("Work changed during rebase; retry resume")
        if record["operation"]["kind"] == "create":
            raise ValueError("Creation cannot be rebound onto an existing project")
        snap = api.snapshot(record["project"])
        if number is None:
            matches = [
                i + 1
                for i, p in enumerate(snap["paths"])
                if str(p) == record.get("sourcePath")
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Source anchor removed or unavailable; inspect deck outline and explicitly choose --page N"
                )
            number = matches[0]
        if not 1 <= number <= len(snap["pages"]):
            raise ValueError("Rebase page out of range")
        if record["operation"]["kind"] in ("move", "merge"):
            raise ValueError(
                "Reopen both current pages before merge/move; ambiguous second anchor is not rebound automatically"
            )
        record = copy.deepcopy(record)
        previous = json.loads((work / "result.json").read_text())
        if previous.get("applied") or (
            previous.get("status") == "ready" and not record.get("rebasedPending")
        ):
            record["candidates"] = [copy.deepcopy(snap["pages"][number - 1])]
        record["rebasedPending"] = not previous.get("applied") and (
            previous.get("status") != "ready" or record.get("rebasedPending", False)
        )
        record.update(
            page=number,
            sourcePath=str(snap["paths"][number - 1]),
            baseToken=api.page_token(snap, number),
        )
        result = _process(_new(work.parent), record, snap, apply=False, render=False)
        result["rebaseReviewRequired"] = True
        result["next"]["hint"] = (
            "Inspect current context and retained candidate before update. Rebase has not published any source changes."
        )
        atomic_write(
            Path(result["work"]) / "result.json", api.json_bytes(result), force=True
        )
        return result


__all__ = [
    "_conflict",
    "_content_signature",
    "_current",
    "_layout_rejection",
    "_new",
    "_process",
    "_read",
    "_root",
    "_split_preserves_content",
    "api",
    "atomic_write",
    "attach_gates",
    "change",
    "check_geometry",
    "create",
    "manifest_paths",
    "open_page",
    "outline",
    "parse_document",
    "rebase",
    "require_pass",
    "resume",
    "source_bytes",
    "update",
    "validate_project",
    "write_geometry",
]
