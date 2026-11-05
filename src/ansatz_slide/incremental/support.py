#!/usr/bin/env python3
"""Replace one slide in an existing PPTX from a modified pptx.yaml project.

The Python source exporter always builds a complete presentation.  This module
uses that complete build as a *candidate* and then applies only the selected
slide to the caller's baseline package.  Shared OOXML parts are never
overwritten: if a candidate dependency differs from a baseline part, it is
copied to a deterministic ``.incN`` part name and the selected slide's
relationships are rewritten to point at the copy.

The public command accepts a baseline PPTX, a modified pptx.yaml project (or
manifest), and a 1-based page index::

    python3 incremental_replace_pptx.py \
      --baseline old.pptx --project edited-deck \
      --page 2 --output edited.pptx

For tests and callers that already have a candidate PPTX, ``--candidate``
skips the full export and exercises the OOXML patcher directly.

The implementation deliberately has a conservative boundary.  A candidate
slide may depend on its own media, chart, notes, layout/master, or theme
parts, but may not depend on a different slide, the presentation part, or
package-global relationship parts.  In those cases the operation fails before
writing the output.
"""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Dict,
    List,
    Set,
    Tuple,
)


class IncrementalReplaceError(RuntimeError):
    """Raised when a slide cannot be replaced without global drift."""


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", REL_NS)
ET.register_namespace("", CONTENT_TYPES_NS)

REL_TAG = f"{{{REL_NS}}}Relationship"
RELATIONSHIPS_TAG = f"{{{REL_NS}}}Relationships"
OVERRIDE_TAG = f"{{{CONTENT_TYPES_NS}}}Override"
DEFAULT_TAG = f"{{{CONTENT_TYPES_NS}}}Default"
SLD_ID_TAG = f"{{{PRESENTATION_NS}}}sldId"

INTERNAL_RELATIONSHIP_TYPES = {
    # This is informational only; TargetMode is the authority.  Keeping the
    # set documents the expected package relationship boundary and makes the
    # error messages easier to interpret when malformed packages are seen.
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _expanded_name(tag: str) -> str:
    """Return a stable QName string independent of namespace prefixes."""

    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        return f"{{{uri}}}{local}"
    return tag


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    return _escape_text(value).replace('"', "&quot;")


def _canonical_xml_node(node: ET.Element) -> str:
    attrs = sorted((_expanded_name(key), value) for key, value in node.attrib.items())
    attr_text = "".join(
        f' {_escape_text(key)}="{_escape_attr(str(value))}"' for key, value in attrs
    )
    text = node.text if node.text and node.text.strip() else ""
    parts = ["<", _expanded_name(node.tag), attr_text, ">"]
    if text:
        parts.append(_escape_text(text))
    for child in list(node):
        parts.append(_canonical_xml_node(child))
        # Pretty-print indentation is not semantic.  OOXML text-bearing
        # elements carry text in child nodes, not in tails.
        tail = child.tail if child.tail and child.tail.strip() else ""
        if tail:
            parts.append(_escape_text(tail))
    parts.extend(["</", _expanded_name(node.tag), ">"])
    return "".join(parts)


def canonical_xml(data: bytes) -> bytes:
    """Canonicalize XML for semantic comparison, not byte comparison.

    Namespace prefixes, XML declarations, self-closing syntax, and indentation
    do not affect the resulting representation.  Child ordering is preserved
    because shape/z-order and run order are semantic in OOXML.
    """

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise IncrementalReplaceError(f"invalid XML while hashing: {exc}") from exc
    return _canonical_xml_node(root).encode("utf-8")


def canonical_relationships(data: bytes) -> bytes:
    """Canonicalize a .rels part with relationship-order independence."""

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise IncrementalReplaceError(f"invalid relationships XML: {exc}") from exc
    if root.tag != RELATIONSHIPS_TAG:
        raise IncrementalReplaceError("relationships part has an unexpected root")
    records: List[Tuple[Tuple[str, str], ...]] = []
    for child in root:
        if child.tag != REL_TAG:
            raise IncrementalReplaceError(
                f"relationships part contains unexpected element: {_local_name(child.tag)}"
            )
        records.append(
            tuple(sorted((_expanded_name(k), str(v)) for k, v in child.attrib.items()))
        )
    # Relationship order is not significant, but IDs, targets, modes, and
    # types are retained in each record because they are semantically used by
    # the referring part.
    records.sort()
    return json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def semantic_digest(part_name: str, data: bytes) -> str:
    """Hash XML semantics and binary content separately."""

    normalized = (
        canonical_relationships(data)
        if part_name.endswith(".rels")
        else canonical_xml(data)
        if part_name.endswith(".xml")
        else data
    )
    return hashlib.sha256(normalized).hexdigest()


def raw_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normal_part_name(name: str) -> str:
    name = name.replace("\\", "/")
    if name.startswith("/"):
        name = name[1:]
    if not name:
        raise IncrementalReplaceError(f"invalid package part path: {name!r}")
    normalized = posixpath.normpath(name)
    if normalized in ("", ".") or normalized.startswith("../") or normalized == "..":
        raise IncrementalReplaceError(f"invalid package part path: {name!r}")
    return normalized


def relationship_part_name(source_part: str) -> str:
    source_part = _normal_part_name(source_part)
    parent = posixpath.dirname(source_part)
    basename = posixpath.basename(source_part)
    return posixpath.join(parent, "_rels", basename + ".rels")


def source_part_from_relationship_part(rels_part: str) -> str:
    rels_part = _normal_part_name(rels_part)
    marker = "/_rels/"
    if marker not in rels_part or not rels_part.endswith(".rels"):
        raise IncrementalReplaceError(
            f"not a conventional relationship part: {rels_part}"
        )
    parent, remainder = rels_part.split(marker, 1)
    return posixpath.join(parent, remainder[: -len(".rels")])


def resolve_relationship_target(source_part: str, target: str) -> Tuple[str, str]:
    """Resolve an internal relationship target and preserve any fragment."""

    if "#" in target:
        target, fragment = target.split("#", 1)
        suffix = "#" + fragment
    else:
        suffix = ""
    if target.startswith("/"):
        resolved = _normal_part_name(target)
    else:
        resolved = _normal_part_name(
            posixpath.join(posixpath.dirname(source_part), target)
        )
    return resolved, suffix


def relative_relationship_target(
    source_part: str, target_part: str, suffix: str
) -> str:
    source_part = _normal_part_name(source_part)
    target_part = _normal_part_name(target_part)
    start = posixpath.dirname(source_part)
    relative = posixpath.relpath(target_part, start=start)
    return relative + suffix


def _is_external_relationship(rel: ET.Element) -> bool:
    return rel.attrib.get("TargetMode", "").lower() == "external"


@dataclass
class Package:
    path: Path
    parts: Dict[str, bytes]
    infos: Dict[str, zipfile.ZipInfo]
    order: List[str]

    @classmethod
    def open(cls, path: Path) -> "Package":
        path = Path(path).expanduser().resolve()
        if not path.is_file() or not zipfile.is_zipfile(path):
            raise IncrementalReplaceError(f"not a PPTX/ZIP package: {path}")
        parts: Dict[str, bytes] = {}
        infos: Dict[str, zipfile.ZipInfo] = {}
        order: List[str] = []
        with zipfile.ZipFile(path, "r") as archive:
            for info in archive.infolist():
                name = _normal_part_name(info.filename)
                if name in parts:
                    raise IncrementalReplaceError(f"duplicate package part: {name}")
                if info.is_dir():
                    # Empty directory entries carry no OOXML semantics, but
                    # retain them in output order for package conservatism.
                    parts[name] = b""
                else:
                    parts[name] = archive.read(info.filename)
                infos[name] = copy.copy(info)
                order.append(name)
            broken = archive.testzip()
            if broken:
                raise IncrementalReplaceError(f"PPTX CRC check failed at {broken}")
        required = {
            "[Content_Types].xml",
            "ppt/presentation.xml",
            "ppt/_rels/presentation.xml.rels",
        }
        missing = sorted(required - set(parts))
        if missing:
            raise IncrementalReplaceError(
                f"PPTX missing required parts: {', '.join(missing)}"
            )
        return cls(path=path, parts=parts, infos=infos, order=order)

    def has(self, part_name: str) -> bool:
        return _normal_part_name(part_name) in self.parts

    def get(self, part_name: str) -> bytes:
        part_name = _normal_part_name(part_name)
        try:
            return self.parts[part_name]
        except KeyError as exc:
            raise IncrementalReplaceError(f"PPTX part not found: {part_name}") from exc


def _parse_xml(pkg: Package, part_name: str) -> ET.Element:
    try:
        return ET.fromstring(pkg.get(part_name))
    except ET.ParseError as exc:
        raise IncrementalReplaceError(f"invalid XML part {part_name}: {exc}") from exc


def _serialize_xml(root: ET.Element) -> bytes:
    return ET.tostring(
        root, encoding="utf-8", xml_declaration=True, short_empty_elements=True
    )


def _relationship_elements(pkg: Package, rels_part: str) -> List[ET.Element]:
    if not pkg.has(rels_part):
        return []
    root = _parse_xml(pkg, rels_part)
    if root.tag != RELATIONSHIPS_TAG:
        raise IncrementalReplaceError(f"invalid .rels root in {rels_part}")
    result: List[ET.Element] = []
    ids: Set[str] = set()
    for child in root:
        if child.tag != REL_TAG:
            raise IncrementalReplaceError(
                f"unexpected element {_local_name(child.tag)} in {rels_part}"
            )
        rel_id = child.attrib.get("Id")
        if not rel_id or rel_id in ids:
            raise IncrementalReplaceError(
                f"duplicate/missing relationship Id in {rels_part}"
            )
        ids.add(rel_id)
        if "Type" not in child.attrib or "Target" not in child.attrib:
            raise IncrementalReplaceError(f"incomplete relationship in {rels_part}")
        result.append(child)
    return result


def _presentation_slides(pkg: Package) -> List[Tuple[str, str, str]]:
    """Return (slide part, sldId value, presentation rel Id) in display order."""

    root = _parse_xml(pkg, "ppt/presentation.xml")
    rels = _relationship_elements(pkg, "ppt/_rels/presentation.xml.rels")
    by_id = {rel.attrib["Id"]: rel for rel in rels}
    sld_id_list = next(
        (child for child in root if _local_name(child.tag) == "sldIdLst"),
        None,
    )
    if sld_id_list is None:
        raise IncrementalReplaceError("presentation.xml has no p:sldIdLst")
    slides: List[Tuple[str, str, str]] = []
    for child in sld_id_list:
        if child.tag != SLD_ID_TAG:
            continue
        rel_id = child.attrib.get(f"{{{OFFICE_REL_NS}}}id")
        slide_id = child.attrib.get("id")
        if not rel_id or not slide_id or rel_id not in by_id:
            raise IncrementalReplaceError(
                "presentation contains an invalid slide relationship"
            )
        rel = by_id[rel_id]
        if rel.attrib.get("TargetMode", "").lower() == "external":
            raise IncrementalReplaceError(
                "presentation slide relationship cannot be external"
            )
        slide_part, _ = resolve_relationship_target(
            "ppt/presentation.xml", rel.attrib["Target"]
        )
        if not slide_part.startswith("ppt/slides/") or not slide_part.endswith(".xml"):
            raise IncrementalReplaceError(
                f"presentation relationship is not a slide: {slide_part}"
            )
        if not pkg.has(slide_part):
            raise IncrementalReplaceError(
                f"presentation references missing slide: {slide_part}"
            )
        slides.append((slide_part, slide_id, rel_id))
    if not slides:
        raise IncrementalReplaceError("presentation contains no slides")
    return slides


def _part_equivalent(
    candidate: Package, candidate_part: str, baseline: Package, baseline_part: str
) -> bool:
    if not baseline.has(baseline_part) or not candidate.has(candidate_part):
        return False
    if semantic_digest(
        candidate_part, candidate.get(candidate_part)
    ) != semantic_digest(baseline_part, baseline.get(baseline_part)):
        return False
    candidate_rels = relationship_part_name(candidate_part)
    baseline_rels = relationship_part_name(baseline_part)
    if candidate.has(candidate_rels) != baseline.has(baseline_rels):
        return False
    if candidate.has(candidate_rels):
        return canonical_relationships(
            candidate.get(candidate_rels)
        ) == canonical_relationships(baseline.get(baseline_rels))
    return True


def _is_forbidden_candidate_part(part_name: str, target_part: str) -> bool:
    part_name = _normal_part_name(part_name)
    if part_name == target_part:
        return False
    if re.fullmatch(r"ppt/slides/slide\d+\.xml", part_name):
        return True
    return part_name in {
        "ppt/presentation.xml",
        "ppt/_rels/presentation.xml.rels",
        "[Content_Types].xml",
        "_rels/.rels",
    }
