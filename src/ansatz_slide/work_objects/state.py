"""绑定修订版本的页面工作对象：候选稿、证据和下一步操作。

每次操作都会在同一谱系中新建工作目录，并明确记录当前 head。源哈希过期会
形成冲突；候选稿须通过结构、源稿预检、几何及所需预览后才发布。保留的候选
稿和诊断信息用于恢复；resume 不会隐式 rebase 或应用候选稿。
"""

import copy
import json
import uuid
from pathlib import Path

from .. import page_api as api
from ..output import attach as attach_gates
from ..project import atomic_write, manifest_paths


def _content_signature(page):
    value = copy.deepcopy(page)
    for element in value.get("elements", []):
        element.pop("bounds", None)
        element.pop("rotation", None)
    value["elements"] = sorted(value.get("elements", []), key=lambda e: e["elementId"])
    return api.json_bytes(value)


def _refresh_narrative(result):
    # Rejected/stale work may carry historical evidence, but must not revive a
    # directive revoked since that evidence was generated.
    from .. import narrative

    try:
        snap = api.snapshot(result["project"])
        number = min(result["page"], len(snap["pages"]))
        result.setdefault("context", {})["narrative"] = narrative.view(snap, number)
    except Exception as exc:
        result.setdefault("context", {})["narrative"] = {
            "status": "unavailable",
            "needsReview": True,
            "reason": str(exc),
            "userRequirements": [],
            "modelProposals": [],
            "meaning": "Current directives could not be read; do not infer that no requirements apply. Reopen the project.",
        }
    return result


def _layout_rejection(work, message):
    result = json.loads((work / "result.json").read_text())
    return attach_gates(
        _refresh_narrative(
            {
                **result,
                "status": "blocked",
                "applied": False,
                "issues": result["issues"]
                + [{"kind": "layout-only", "message": message}],
                "rejectedChange": True,
            }
        )
    )


def _split_preserves_content(originals, candidates):
    # Redistribute elements; do not erase/rewrite content to silence a geometry gate.
    def elements(pages):
        result = []
        for page in pages:
            for element in page.get("elements", []):
                element = copy.deepcopy(element)
                element.pop("bounds", None)
                element.pop("rotation", None)
                result.append(api.json_bytes(element))
        return sorted(result)

    if elements(originals) != elements(candidates):
        return False
    original_notes = [p.get("notes", "") for p in originals if p.get("notes")]
    candidate_notes = [p.get("notes", "") for p in candidates if p.get("notes")]
    return original_notes == candidate_notes


def _new(folder):
    path = folder / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def _root(project):
    folder = api.session_path(Path(project) / ".ansatz" / "work")
    folder.mkdir(parents=True, exist_ok=True)
    return _new(folder)


def _read(work):
    work = api.session_path(work)
    record = json.loads((work / "record.json").read_text())
    if record.get("format") != 1:
        raise ValueError("Unsupported page work format")
    return work, record


def _finish(work, record, result):
    result = {
        "format": "page-work-v1",
        "work": str(work),
        "resumeToken": str(work.parent),
        **result,
    }
    attach_gates(result)
    result["next"] = {
        "command": ["ansatz-slide", "page", "update", str(work)],
        "hint": "Modify a candidate with --element ID --changes FILE or --content FILE; no arguments retries the retained candidate.",
    }
    result["repair"] = {
        "candidateFiles": [i["editable"] for i in result.get("candidates", [])],
        "rules": "Geometry failure: bounds/rotation/order only, or content-preserving split. Text/table overflow: use measured required dimensions, then check geometry again. No content is silently removed.",
        "recoveryCommand": ["ansatz-slide", "page", "resume", str(work.parent)],
    }
    atomic_write(work / "record.json", api.json_bytes(record))
    atomic_write(work / "result.json", api.json_bytes(result))
    api.session_path(work.parent)
    atomic_write(
        work.parent / "head.json", api.json_bytes({"work": str(work)}), force=True
    )
    return result


def _conflict(work, record, message):
    previous = json.loads((work / "result.json").read_text())
    for role in ("previous", "current", "next"):
        item = previous.get("context", {}).get(role)
        if item:
            item["needsReview"] = True
    return attach_gates(
        _refresh_narrative(
            {
                **previous,
                "status": "conflict",
                "applied": False,
                "issues": [{"kind": "conflict", "message": message}],
                "next": {
                    "command": ["ansatz-slide", "page", "rebase", str(work.parent)],
                    "hint": "Rebase resolves the latest candidate against its source path, not the old page number. If the source was removed, explicitly supply --page. Review the rebased candidate before update; no automatic overwrite.",
                },
            }
        )
    )


def _current(work, record):
    head = json.loads((work.parent / "head.json").read_text())
    if head["work"] != str(work):
        raise ValueError(
            "This work reference was superseded; use the work returned by the last operation"
        )
    if record["operation"]["kind"] == "create":
        if manifest_paths(record["project"]):
            raise ValueError("Project was already created")
        return None
    snap = api.snapshot(record["project"])
    if not 1 <= record["page"] <= len(snap["pages"]):
        raise ValueError(
            "Original page index no longer exists; rebase the retained work"
        )
    if record["baseToken"] != api.page_token(snap, record["page"]):
        raise ValueError("Source or related assets changed after this work was opened")
    return snap
