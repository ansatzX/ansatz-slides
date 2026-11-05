"""页面级快照、预览和可恢复的源文件发布。

本 API 将编辑会话绑定到页面与源文件哈希，校验并预览候选稿后，只发布目标
页面或清单顺序变更。令牌用于发现过期输入，但不能阻止外部写入，因此发布
前后还会复查哈希，并保留备份以便回滚。
"""

import copy
import re
import tempfile
import uuid
from pathlib import Path

from .. import export_pptx
from ..package import inspect_pptx
from ..project import (
    image_objects,
    resolve_images,
)
from ..rendering import render_pptx
from ..typography import (
    check_page as measure_text,
)
from ..typography import (
    check_pages as measure_pages,
)
from ..typography import (
    require_pass as require_text,
)
from ..validation import safe_path, validate_project
from .state import context, json_bytes, session_path, sha, snapshot, title, unchanged


def preview(snap, number, candidate, session, width):
    """测量单页候选稿；几何和文本检查通过后才渲染。"""
    if not isinstance(candidate, dict) or "pages" in candidate:
        raise ValueError(
            "Edit input must be exactly one page object, not a deck or page list"
        )
    pages = copy.deepcopy(snap["pages"])
    pages[number - 1] = candidate
    validate_project(snap["manifest"], pages, snap["root"])
    selected = {**copy.deepcopy(snap["manifest"]), "pages": [copy.deepcopy(candidate)]}
    assets = {}
    for image in image_objects(selected):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            p = safe_path(snap["root"], image["src"], "image")
            assets[str(p)] = sha(p.read_bytes())
    versions = session / "versions"
    versions.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preview-", dir=versions) as scratch:
        stage = Path(scratch).resolve()
        from ..occupancy import write_geometry

        geometry = write_geometry(
            snap["manifest"]["size"], candidate, stage / "geometry"
        )
        image_name = None
        typography = None
        renderer = {
            "name": None,
            "reason": "Geometry precheck blocked; no PPTX or Office render created",
        }
        if geometry["status"] == "passed":
            typography = measure_text(
                snap["manifest"]["size"],
                candidate,
                snap["manifest"].get("theme", {}),
                session / ("text-fit-" + uuid.uuid4().hex),
            )
            typography["page"] = number
            require_text(typography)
            data = export_pptx(
                selected,
                {
                    "images": resolve_images(
                        selected, snap["root"], allow_remote=False
                    ),
                    "slideTransition": {"effect": "none", "speed": "fast"},
                },
            )
            if inspect_pptx(data)["pageCount"] != 1:
                raise RuntimeError("Preview must contain exactly one page")
            (stage / "page.pptx").write_bytes(data)
            renderer = render_pptx(stage / "page.pptx", stage, width)
            images = list(stage.glob("page-*.png"))
            if len(images) != 1 or not images[0].read_bytes().startswith(
                b"\x89PNG\r\n\x1a\n"
            ):
                raise RuntimeError("Renderer must produce exactly one PNG")
            image_name = images[0].name
        if not unchanged(snap["tracked"]) or not unchanged(assets):
            raise RuntimeError(
                "Source or assets changed during preview; retry page check"
            )
        target = versions / uuid.uuid4().hex
        geometry["files"] = {
            k: str(target / "geometry" / Path(v).name)
            for k, v in geometry["files"].items()
        }
        (stage / "geometry" / "report.json").write_bytes(json_bytes(geometry))
        stage.rename(target)
    return {
        "image": str((target / image_name).relative_to(session))
        if image_name
        else None,
        "previewPptx": str((target / "page.pptx").relative_to(session))
        if image_name
        else None,
        "renderer": renderer,
        "geometry": geometry,
        "typography": typography,
        "_assetHashes": assets,
    }


def preview_batch(snap, candidates, session, width):
    """Check a candidate batch and render bounded groups, without publishing it."""
    from ..occupancy import require_pass, write_geometry

    validate_project(snap["manifest"], candidates, snap["root"])
    selected = {**copy.deepcopy(snap["manifest"]), "pages": copy.deepcopy(candidates)}
    assets = {}
    for image in image_objects(selected):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            path = safe_path(snap["root"], image["src"], "image")
            assets[str(path)] = sha(path.read_bytes())
    geometries = []
    for number, candidate in enumerate(candidates, 1):
        geometry = write_geometry(
            snap["manifest"]["size"], candidate, session / f"geometry-{number}"
        )
        try:
            require_pass(geometry, label=f"candidate {number}")
        except Exception as exc:
            exc.candidate_number = number
            raise
        geometries.append(geometry)
    reports = measure_pages(
        snap["manifest"]["size"],
        candidates,
        snap["manifest"].get("theme", {}),
        session / "text-fit",
    )
    for report in reports:
        try:
            require_text(report)
        except Exception as exc:
            exc.candidate_number = report["page"]
            raise
    evidence = []
    for start in range(0, len(candidates), 16):
        group = candidates[start : start + 16]
        stage = session / f"render-{start + 1}"
        stage.mkdir()
        rendered = {**selected, "pages": copy.deepcopy(group)}
        data = export_pptx(
            rendered,
            {
                "images": resolve_images(rendered, snap["root"], allow_remote=False),
                "slideTransition": {"effect": "none", "speed": "fast"},
            },
        )
        if inspect_pptx(data)["pageCount"] != len(group):
            raise RuntimeError("Batch preview page count mismatch")
        (stage / "pages.pptx").write_bytes(data)
        renderer = render_pptx(stage / "pages.pptx", stage, width)
        images = sorted(
            stage.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1])
        )
        if len(images) != len(group) or any(
            not image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for image in images
        ):
            raise RuntimeError("Batch renderer must produce one PNG per candidate")
        for offset, image in enumerate(images):
            index = start + offset
            evidence.append(
                {
                    "image": str(image.relative_to(session)),
                    "previewPptx": str((stage / "pages.pptx").relative_to(session)),
                    "renderer": renderer,
                    "geometry": geometries[index],
                    "typography": reports[index],
                    "_assetHashes": assets,
                }
            )
    if not unchanged(snap["tracked"]) or not unchanged(assets):
        raise RuntimeError("Source or assets changed during batch preview; retry")
    return evidence


def response(session, state, snap):
    number = state["page"]
    return {
        "session": str(session),
        "page": number,
        "pageCount": len(snap["pages"]),
        "token": state["token"],
        "sourcePage": str(snap["paths"][number - 1]),
        "editablePage": str(session / "page.page.yaml"),
        "pageSource": snap["pages"][number - 1],
        "canvas": snap["manifest"]["size"],
        "theme": snap["manifest"].get("theme"),
        "assetRoot": str(snap["root"]),
        "adjacentContext": context(snap, number),
        "image": str(session / state["image"]) if state["image"] else None,
        "previewPptx": str(session / state["previewPptx"])
        if state["previewPptx"]
        else None,
        "renderer": state["renderer"],
        "geometry": state["geometry"],
        "typography": state.get("typography"),
        "focus": (
            "Fix geometry using the editable page and geometry issues; no PPTX is generated until it passes."
            if state["geometry"]["status"] == "blocked"
            else "Open this page image. Check its claim/evidence and layout; use page patch for one element or page edit for page composition, then inspect the returned image."
        ),
        "nextCommand": [
            "ansatz-slide",
            "page",
            "edit",
            str(session),
            "--token",
            state["token"],
        ],
    }


def check_deck(project):
    snap = snapshot(project)
    return {
        "project": str(snap["manifestPath"]),
        "pageCount": len(snap["pages"]),
        "outline": [
            {
                "page": i + 1,
                "sourcePage": str(snap["paths"][i]),
                "title": title(p),
                "pageType": p.get("pageType"),
            }
            for i, p in enumerate(snap["pages"])
        ],
        "focus": "Read the whole argument, premises and ending. Expand a specific page with page check when detail is needed; use local edit, split or adjacent merge operations.",
        "editScope": "This command is read-only and does not expose a bulk-edit operation.",
    }


def check_overlap(project, number, output, cell_size=1):
    from ..occupancy import write_precheck

    snap = snapshot(project)
    if number < 1 or number > len(snap["pages"]):
        raise ValueError("Page out of range")
    output = session_path(output)
    if output.exists():
        raise FileExistsError("Use a new precheck output directory")
    report = write_precheck(
        snap["manifest"]["size"], snap["pages"][number - 1], output, cell_size
    )
    if not unchanged(snap["tracked"]):
        raise RuntimeError("Source changed during precheck; retry")
    return {"page": number, "sourcePage": str(snap["paths"][number - 1]), **report}
