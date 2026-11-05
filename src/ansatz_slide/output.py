"""Default stdout projection; never modifies saved evidence or acceptance gates."""

import copy
from pathlib import Path


def compact_result(result):
    result = copy.deepcopy(result)
    if result.get("format") != "page-work-v1":
        if isinstance(result.get("pages"), list):
            result["pages"] = [compact_result(p) for p in result["pages"]]
        return result
    result["outputMode"] = "compact"
    # result.json is the persisted revision evidence, not necessarily the live
    # conflict/directive response. Current status, issues and gates stay inline.
    result["revisionEvidence"] = (
        str(Path(result["work"]) / "result.json") if result.get("work") else None
    )
    for key in ("candidates", "operationCandidates"):
        for item in result.get(key, []):
            if result.get("applied"):
                item.pop("page", None)
            geometry = item.get("geometry")
            if geometry:
                geometry.pop("matrices", None)
                geometry.pop("elements", None)
                geometry.pop("overlaps", None)
                geometry.pop("approvedOverlaps", None)
    for item in result.get("blockingPages", []):
        item.get("geometry", {}).pop("matrices", None)
        item.get("geometry", {}).pop("elements", None)
    reports = result.get("textFit", [])
    if isinstance(reports, dict):
        reports = [reports]
    for report in reports:
        if not isinstance(report, dict):
            continue
        elements = report.get("elements", [])
        report.setdefault("checkedElementCount", len(elements))
        report["elements"] = [e for e in elements if e.get("status") != "passed"]
    return result


def attach(result):
    context = result.setdefault("context", {})
    context.setdefault("previous", None)
    context.setdefault("current", None)
    context.setdefault("next", None)
    requirements = []
    suggestions = []
    for role in ("previous", "current", "next"):
        entry = context.get(role)
        if not entry:
            continue
        intent = entry.get("intent") or {}
        source = {
            "role": role,
            "page": entry["page"],
            "source": entry["source"],
            "needsReview": entry.get("needsReview", True),
            "origin": "model-authored outline",
            "kind": "model_proposal",
            "status": "active",
        }
        requirements.extend(
            {**source, "text": text} for text in intent.get("requirements", [])
        )
        suggestions.extend(
            {**source, "text": text} for text in intent.get("suggestions", [])
        )
    narrative = context.get("narrative") or {}
    user_requirements = narrative.get("userRequirements", [])
    model_proposals = requirements + narrative.get("modelProposals", [])
    restrictions = []
    for candidate in result.get("candidates", []):
        if candidate.get("layoutOnly"):
            restrictions.append(
                {
                    "candidate": candidate["index"],
                    "rule": "layout-only",
                    "allowedChanges": ["bounds", "rotation", "element order"],
                    "preserve": [
                        "content",
                        "styles",
                        "elements",
                        "overlap declarations",
                    ],
                }
            )
        if candidate.get("geometryFailures", 0) >= 3:
            suggestions.append(
                {
                    "candidate": candidate["index"],
                    "origin": "geometry retry count",
                    "code": "consider-split",
                    "optional": True,
                    "text": "Three consecutive geometry checks failed. The page may be too crowded; consider a content-preserving split. Further layout repair is also allowed.",
                }
            )
    result["gates"] = {
        "hard": {
            "owner": "program",
            "rules": [
                "source version and edit scope",
                "schema and resources",
                "geometry bounds and declared overlaps",
                "layout-only repair after geometry failure",
                "measured native text must fit its frame",
                "successful rendering before source publication",
            ],
            "blockingIssues": result.get("issues", [])
            if not result.get("applied")
            else [],
            "activeRestrictions": restrictions,
            "applied": result.get("applied"),
        },
        "live": {
            "owner": "model",
            "requirements": requirements + user_requirements,
            "userRequirements": user_requirements,
            "modelProposals": model_proposals,
            "unresolvedDirectives": narrative.get("unresolvedDirectives", []),
            "suggestions": [{**s, "optional": True} for s in suggestions],
            "evaluation": "not evaluated by the CLI",
            "instruction": "Honor semantic requirements using the three-page logic and evidence. Suggestions are optional. Program success is not semantic acceptance.",
        },
    }
    result["gates"]["visual"] = {
        "owner": "model",
        "status": "not_evaluated",
        "instruction": "Open the actual PPTX render to assess typography, hierarchy, crops and readability. Geometry/text-fit passes and successful rendering do not constitute visual acceptance.",
    }
    result["gates"]["facts"] = {
        "origin": "program",
        "work": result.get("work"),
        "state": "historical" if result.get("status") == "conflict" else "candidate",
        "applied": result.get("applied", False),
        "evidenceFields": ["candidates[].geometry", "textFit"],
        "meaning": "Measured/schema/geometry facts only; no semantic acceptance. Evidence belongs to this work candidate; failed publication does not update formal sources.",
    }
    return result
