"""绑定修订版本的页面工作对象：候选稿、证据和下一步操作。

每次操作都会在同一谱系中新建工作目录，并明确记录当前 head。源哈希过期会
形成冲突；候选稿须通过结构、源稿预检、几何及所需预览后才发布。保留的候选
稿和诊断信息用于恢复；resume 不会隐式 rebase 或应用候选稿。
"""

import json
import traceback
import uuid
from pathlib import Path

from .. import narrative as outline
from .. import page_api as api
from ..occupancy import check_geometry, require_pass, write_geometry
from ..project import atomic_write, manifest_paths, source_bytes
from ..validation import validate_project
from .state import _current, _finish, _new, _read


def _candidates(work, record, snap):
    """保存可编辑候选稿，并收集结构、语义提示和几何证据。"""
    results = []
    issues = []
    size = record["settings"]["size"] if snap is None else snap["manifest"]["size"]
    root = Path(record["project"]) if snap is None else snap["root"]
    for i, candidate in enumerate(record["candidates"], 1):
        path = work / f"candidate-{i}.page.yaml"
        atomic_write(path, api.json_bytes(candidate))
        item = {
            "index": i,
            "page": candidate,
            "editable": str(path),
            "geometry": None,
            "preview": None,
        }
        try:
            geometry = write_geometry(size, candidate, work / f"geometry-{i}")
            item["geometry"] = geometry
        except Exception as exc:
            issues.append(
                {"candidate": i, "kind": "geometry-input", "message": str(exc)}
            )
        try:
            manifest = {
                **(record["settings"] if snap is None else snap["manifest"]),
                "pages": [str(path.relative_to(root))],
            }
            validate_project(manifest, [candidate], root)
            from ..preflight import (
                analyze,
            )
            from ..preflight import (
                require_pass as require_sources,
            )
            from ..preflight import (
                summary as source_summary,
            )

            source_preflight = analyze(
                size, [candidate], root, allow_remote=False, theme=manifest.get("theme")
            )
            item["sourcePreflight"] = source_summary(source_preflight)
            require_sources(source_preflight)
        except Exception as exc:
            issues.append({"candidate": i, "kind": "schema", "message": str(exc)})
        if item["geometry"] is not None and item["geometry"]["status"] == "blocked":
            try:
                require_pass(item["geometry"])
            except ValueError as exc:
                issues.append({"candidate": i, "kind": "geometry", "message": str(exc)})
        results.append(item)
    return results, issues


def _adapter(work, record, snap):
    """Keep existing source transaction guarantees behind the new interface."""
    session = work / "adapter"
    session.mkdir()
    original = snap["pages"][record["page"] - 1]
    state = {
        "format": 1,
        "project": str(snap["manifestPath"]),
        "page": record["page"],
        "token": record["baseToken"],
        "width": record["width"],
        "draftHash": api.sha(api.json_bytes(original)),
    }
    api.session_write(session, "page.page.yaml", api.json_bytes(original))
    api.session_write(session, "session.json", api.json_bytes(state))
    return session


def _execute(work, record, snap, items):
    operation = record["operation"]
    kind = operation["kind"]
    if kind == "create":
        root = Path(record["project"])
        manifest = {
            **record["settings"],
            "pages": [str(Path(item["editable"]).relative_to(root)) for item in items],
        }
        fake = {
            "manifest": manifest,
            "pages": record["candidates"],
            "root": root,
            "tracked": {},
        }
        rendered = [
            api.preview(fake, i, candidate, work, record["width"])
            for i, candidate in enumerate(record["candidates"], 1)
        ]
        assets = {}
        for evidence in rendered:
            for path, digest in evidence["_assetHashes"].items():
                if path in assets and assets[path] != digest:
                    raise RuntimeError(
                        "Assets changed between page previews; retry creation"
                    )
                assets[path] = digest
        with api.lock(root / ".ansatz-page-edit.lock"):
            if manifest_paths(root):
                raise ValueError("Project already has a manifest")
            if not api.unchanged(assets):
                raise RuntimeError("Assets changed after preview; retry creation")
            names = [f"page-{uuid.uuid4().hex}.page.yaml" for _ in items]
            for name, candidate in zip(names, record["candidates"]):
                atomic_write(root / name, source_bytes(api.json_bytes(candidate)))
            manifest_path = root / "pptx.yaml"
            data = source_bytes(api.json_bytes({**record["settings"], "pages": names}))
            if manifest_paths(root) or not api.unchanged(assets):
                raise RuntimeError(
                    "Project or assets changed before publication; retry creation"
                )
            atomic_write(manifest_path, data)
            try:
                if manifest_paths(root) != [manifest_path] or not api.unchanged(assets):
                    raise RuntimeError(
                        "Project or assets changed during publication; retry creation"
                    )
            except Exception:
                from ..file_transactions import retract_created

                retract_created(manifest_path, api.sha(data))
                raise
        return {
            "page": 1,
            "textFit": [r["typography"] for r in rendered],
            "newPages": [
                {
                    "page": i,
                    "image": str(work / r["image"]),
                    "previewPptx": str(work / r["previewPptx"]),
                }
                for i, r in enumerate(rendered, 1)
            ],
        }
    session = _adapter(work, record, snap)
    token = record["baseToken"]
    contents = [Path(item["editable"]) for item in items]
    if kind == "edit":
        return api.edit_page(session, token, contents[0])
    if kind in ("insert", "split", "merge", "move", "remove"):
        other_session = None
        other_token = None
        if kind in ("merge", "move"):
            other_work, other = _read(operation["other"])
            other_snap = _current(other_work, other)
            if other["project"] != record["project"]:
                raise ValueError("Other work belongs to a different project")
            if json.loads((other_work / "result.json").read_text())["status"] not in (
                "ready",
                "applied",
            ):
                raise ValueError("Other work has a pending candidate; resolve it first")
            other_session = _adapter(_new(work), other, other_snap)
            other_token = other["baseToken"]
        if kind in ("split", "merge"):
            return api.reshape_pages(
                session, token, contents, other_session, other_token
            )
        return api.change_order(
            session,
            token,
            kind,
            content=contents[0] if kind == "insert" else None,
            position=operation.get("position", "after"),
            allow_duplicates=operation.get("allowDuplicates", False),
            anchor_session=other_session,
            anchor_token=other_token,
        )
    raise ValueError("Unknown work operation")


def _process(work, record, snap, *, apply, render=True):
    """对保留候选稿执行检查、可选预览和请求操作。

    检查受阻时仍可按路径修复候选稿。请求 apply 时，由 ``_execute`` 调用现有
    页面 API 事务，从而避免工作对象层重复实现发布逻辑。
    """
    items, issues = _candidates(work, record, snap)
    previous = record.get("geometryFailures", [0] * len(items))
    failures = []
    for i, item in enumerate(items):
        count = previous[i] if i < len(previous) else 0
        geometry = item["geometry"]
        if geometry is not None:
            count = count + 1 if geometry["status"] == "blocked" else 0
        failures.append(count)
        item["geometryFailures"] = count
        item["layoutOnly"] = count > 0
        item["guidance"] = (
            "Only change bounds/rotation; preserve content, styles and elements."
            if count
            else ""
        )
        if count >= 3:
            item["guidance"] += (
                " Three consecutive geometry checks failed. The page may be too crowded; consider splitting it while retaining all content."
            )
    record["geometryFailures"] = failures
    result = {
        "status": "blocked" if issues else "ready",
        "applied": False,
        "project": record["project"],
        "page": record["page"],
        "operation": record["operation"],
        "candidates": items,
        "issues": issues,
        "context": outline.context(snap, record["page"])
        if snap is not None
        else {"previous": None, "current": None, "next": None},
    }
    if not issues:
        try:
            if apply:
                outcome = _execute(work, record, snap, items)
                result.update(status="applied", applied=True)
                result["textFit"] = outcome.get("textFit", [outcome.get("typography")])
                project = (
                    Path(record["project"]) / "pptx.yaml"
                    if snap is None
                    else snap["manifestPath"]
                )
                updated = api.snapshot(project)
                number = outcome.get(
                    "page",
                    outcome.get("newPages", [{"page": record["page"]}])[0]["page"],
                )
                record.update(
                    project=str(project),
                    page=number,
                    sourcePath=str(updated["paths"][number - 1]),
                    baseToken=api.page_token(updated, number),
                    operation={"kind": "edit"},
                    candidates=[updated["pages"][number - 1]],
                    geometryFailures=[0],
                )
                result.update(
                    status="applied",
                    applied=True,
                    project=str(project),
                    page=number,
                    context=outline.context(updated, number),
                    effect={
                        key: outcome[key]
                        for key in (
                            "changedPages",
                            "replacedPages",
                            "retiredSources",
                            "removedSource",
                            "recoverySource",
                            "recoveryManifest",
                            "pageCount",
                        )
                        if key in outcome
                    },
                )
                if "newPages" in outcome:
                    for item, preview in zip(items, outcome["newPages"]):
                        item["preview"] = {
                            "image": preview["image"],
                            "pptx": preview["previewPptx"],
                        }
                elif outcome.get("image"):
                    items[0]["preview"] = {
                        "image": outcome["image"],
                        "pptx": outcome["previewPptx"],
                    }
                # The returned primary candidate always matches the next operation.
                if len(items) != 1 or items[0]["page"] != record["candidates"][0]:
                    result["operationCandidates"] = items
                    if items[0]["page"] == record["candidates"][0]:
                        result["candidates"] = [items[0]]
                    else:
                        after = _new(work)
                        current_items, current_issues = _candidates(
                            after, record, updated
                        )
                        result["candidates"] = current_items
                        result["issues"].extend(current_issues)
                        rendered = api.preview(
                            updated,
                            number,
                            record["candidates"][0],
                            after,
                            record["width"],
                        )
                        current_items[0]["preview"] = {
                            "image": str(after / rendered["image"])
                            if rendered["image"]
                            else None,
                            "pptx": str(after / rendered["previewPptx"])
                            if rendered["previewPptx"]
                            else None,
                        }
            elif render:
                rendered = api.preview(
                    snap, record["page"], record["candidates"][0], work, record["width"]
                )
                result["textFit"] = [rendered["typography"]]
                items[0]["preview"] = {
                    "image": str(work / rendered["image"])
                    if rendered["image"]
                    else None,
                    "pptx": str(work / rendered["previewPptx"])
                    if rendered["previewPptx"]
                    else None,
                }
        except Exception as exc:
            if hasattr(exc, "report"):
                result["textFit"] = [exc.report]
            if not result["applied"]:
                result["status"] = (
                    "conflict"
                    if "concurrent" in str(exc).lower()
                    or "changed" in str(exc).lower()
                    or "stale" in str(exc).lower()
                    else "blocked"
                )
            diagnostic = work / "execution-error.txt"
            diagnostic.write_text(traceback.format_exc(), encoding="utf-8")
            result["issues"].append(
                {
                    "kind": "execution",
                    "message": str(exc),
                    "diagnostic": str(diagnostic),
                }
            )
            if (
                not result["applied"]
                and snap is not None
                and "Geometry precheck failed" in str(exc)
            ):
                result["blockingPages"] = []
                for number, page in enumerate(snap["pages"], 1):
                    report = check_geometry(snap["manifest"]["size"], page)
                    if report["status"] == "blocked":
                        report = write_geometry(
                            snap["manifest"]["size"],
                            page,
                            work / f"blocking-page-{number}",
                        )
                        result["blockingPages"].append(
                            {
                                "page": number,
                                "source": str(snap["paths"][number - 1]),
                                "geometry": report,
                            }
                        )
    if not apply and not render:
        result["previewStatus"] = "not_requested"
        result["textFit"] = [
            {
                "status": "unverified",
                "reason": "Read-only open skipped rendering; update still requires text measurement and preview.",
            }
        ]
    return _finish(work, record, result)
