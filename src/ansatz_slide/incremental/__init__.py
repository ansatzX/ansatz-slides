"""Replace one slide in an existing PPTX from a modified pptx.yaml project.

The Python source exporter always builds a complete presentation.  This module
uses that complete build as a *candidate* and then applies only the selected
slide to the caller's baseline package.  Shared OOXML parts are never
overwritten: if a candidate dependency differs from a baseline part, it is
copied to a deterministic ``.incN`` part name and the selected slide's
relationships are rewritten to point at the copy.

The public command accepts a baseline PPTX, a modified pptx.yaml project (or
manifest), and a 1-based page index::

    python3 incremental_replace_pptx.py       --baseline old.pptx --project edited-deck       --page 2 --output edited.pptx

For tests and callers that already have a candidate PPTX, ``--candidate``
skips the full export and exercises the OOXML patcher directly.

The implementation deliberately has a conservative boundary.  A candidate
slide may depend on its own media, chart, notes, layout/master, or theme
parts, but may not depend on a different slide, the presentation part, or
package-global relationship parts.  In those cases the operation fails before
writing the output.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Set

from .patcher import IncrementalPatcher
from .support import (
    CONTENT_TYPES_NS,
    DEFAULT_TAG,
    INTERNAL_RELATIONSHIP_TYPES,
    OFFICE_REL_NS,
    OVERRIDE_TAG,
    PRESENTATION_NS,
    REL_NS,
    REL_TAG,
    RELATIONSHIPS_TAG,
    SLD_ID_TAG,
    XML_NS,
    IncrementalReplaceError,
    Package,
    _canonical_xml_node,
    _escape_attr,
    _escape_text,
    _expanded_name,
    _is_external_relationship,
    _is_forbidden_candidate_part,
    _local_name,
    _normal_part_name,
    _parse_xml,
    _part_equivalent,
    _presentation_slides,
    _relationship_elements,
    _serialize_xml,
    canonical_relationships,
    canonical_xml,
    raw_digest,
    relationship_part_name,
    relative_relationship_target,
    resolve_relationship_target,
    semantic_digest,
    source_part_from_relationship_part,
)


def _clone_info(info: Optional[zipfile.ZipInfo], filename: str) -> zipfile.ZipInfo:
    if info is None:
        clone = zipfile.ZipInfo(filename)
        clone.compress_type = zipfile.ZIP_DEFLATED
        return clone
    clone = copy.copy(info)
    clone.filename = filename
    return clone


def write_package(
    baseline: Package,
    output_path: Path,
    replacements: Mapping[str, bytes],
    additions: Mapping[str, bytes],
    remove: Set[str],
) -> None:
    """保留基线部件顺序写入暂存 ZIP，再追加新部件。"""
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(temp, "w") as archive:
            archive.comment = b""
            for name in baseline.order:
                if name in remove:
                    continue
                info = baseline.infos[name]
                data = replacements.get(name, baseline.parts[name])
                archive.writestr(
                    _clone_info(info, name),
                    data,
                    compress_type=info.compress_type,
                )
            for name in sorted(additions):
                if name in baseline.parts or name in remove:
                    raise IncrementalReplaceError(
                        f"cannot add colliding package part: {name}"
                    )
                archive.writestr(_clone_info(None, name), additions[name])
        temp.replace(output_path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def replace_from_candidate(
    baseline_path: Path,
    candidate_path: Path,
    page_index: int,
    output_path: Path,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """先移植并验证，再发布由候选稿生成的包。"""
    from ..project import atomic_write

    output_path = Path(output_path).expanduser().resolve()
    if output_path in {Path(baseline_path).resolve(), Path(candidate_path).resolve()}:
        raise IncrementalReplaceError("Output must not overwrite baseline or candidate")
    if output_path.exists() and not force:
        raise IncrementalReplaceError(f"output already exists: {output_path}")
    baseline = Package.open(baseline_path)
    candidate = Package.open(candidate_path)
    patcher = IncrementalPatcher(baseline, candidate, page_index)
    patcher.build()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staged = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.verified")
    try:
        write_package(
            baseline, staged, patcher.replacements, patcher.additions, patcher.remove
        )
        report = patcher.verify(Package.open(staged))
        atomic_write(output_path, staged.read_bytes(), force=force)
    finally:
        staged.unlink(missing_ok=True)
    report.update(
        {
            "baseline": str(Path(baseline_path).expanduser().resolve()),
            "candidate": str(Path(candidate_path).expanduser().resolve()),
            "output": str(Path(output_path).expanduser().resolve()),
            "outputBytes": Path(output_path).stat().st_size,
        }
    )
    return report


def replace_from_project(
    baseline_path: Path,
    project: Path,
    page_index: int,
    output_path: Path,
    *,
    allow_remote: bool = True,
    transition: str = "fade",
    force: bool = False,
    keep_candidate: bool = False,
) -> Dict[str, Any]:
    """先导出完整候选包，再移植一个经过检查的页面。"""
    from ..project import find_manifest, image_objects, load_project
    from ..validation import safe_path

    pptd, project_root = load_project(project)
    protected = {Path(baseline_path).resolve(), find_manifest(project)}
    protected.update(
        safe_path(project_root, page["pagePath"], "page") for page in pptd["pages"]
    )
    for image in image_objects(pptd):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            protected.add(safe_path(project_root, image["src"], "image"))
    if Path(output_path).resolve() in protected:
        raise IncrementalReplaceError(
            "Output must not overwrite baseline, source or assets"
        )
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path = output_path.with_name(
        f".{output_path.stem}.candidate.{uuid.uuid4().hex}.pptx"
    )
    try:
        from ..project import export_project

        export_project(
            project, candidate_path, transition=transition, allow_remote=allow_remote
        )
        report = replace_from_candidate(
            baseline_path,
            candidate_path,
            page_index,
            output_path,
            force=force,
        )
        if keep_candidate:
            report["candidateKept"] = str(candidate_path)
            return report
        return report
    finally:
        if not keep_candidate:
            try:
                candidate_path.unlink(missing_ok=True)
            except OSError:
                pass


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replace exactly one slide in a baseline PPTX from a modified pptx.yaml "
            "project while preserving non-target OOXML semantics."
        )
    )
    parser.add_argument(
        "--baseline", required=True, type=Path, help="existing PPTX to preserve"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--project", type=Path, help="modified pptx.yaml manifest or project directory"
    )
    source.add_argument(
        "--candidate", type=Path, help="already-exported candidate PPTX (test/debug)"
    )
    parser.add_argument(
        "--page",
        required=True,
        type=int,
        help="1-based page index to replace",
    )
    parser.add_argument("--output", "-o", required=True, type=Path, help="output PPTX")
    parser.add_argument(
        "--offline", action="store_true", help="Reject HTTP image resources"
    )
    parser.add_argument(
        "--transition",
        choices=("fade", "none"),
        default="fade",
        help="transition used when exporting the modified pptx.yaml candidate",
    )
    parser.add_argument(
        "--keep-candidate", action="store_true", help="retain the full candidate PPTX"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace an existing output"
    )
    parser.add_argument(
        "--report", type=Path, help="write the verification report as JSON"
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.candidate is not None:
            report = replace_from_candidate(
                args.baseline,
                args.candidate,
                args.page,
                args.output,
                force=args.force,
            )
        else:
            report = replace_from_project(
                args.baseline,
                args.project,
                args.page,
                args.output,
                allow_remote=not args.offline,
                transition=args.transition,
                force=args.force,
                keep_candidate=args.keep_candidate,
            )
    except (ValueError, IncrementalReplaceError, OSError) as exc:
        print(f"incremental PPTX replacement failed: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

__all__ = [
    "CONTENT_TYPES_NS",
    "DEFAULT_TAG",
    "INTERNAL_RELATIONSHIP_TYPES",
    "IncrementalPatcher",
    "IncrementalReplaceError",
    "OFFICE_REL_NS",
    "OVERRIDE_TAG",
    "PRESENTATION_NS",
    "Package",
    "RELATIONSHIPS_TAG",
    "REL_NS",
    "REL_TAG",
    "SLD_ID_TAG",
    "XML_NS",
    "_canonical_xml_node",
    "_escape_attr",
    "_escape_text",
    "_expanded_name",
    "_is_external_relationship",
    "_is_forbidden_candidate_part",
    "_local_name",
    "_normal_part_name",
    "_parse_xml",
    "_part_equivalent",
    "_presentation_slides",
    "_relationship_elements",
    "_serialize_xml",
    "canonical_relationships",
    "canonical_xml",
    "main",
    "parse_args",
    "raw_digest",
    "relationship_part_name",
    "relative_relationship_target",
    "replace_from_candidate",
    "replace_from_project",
    "resolve_relationship_target",
    "semantic_digest",
    "source_part_from_relationship_part",
    "write_package",
]
