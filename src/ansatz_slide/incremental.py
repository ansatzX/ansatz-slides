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

import argparse
import copy
import hashlib
import json
import posixpath
import re
import sys
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
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


@dataclass
class IncrementalPatcher:
    baseline: Package
    candidate: Package
    target_index: int
    baseline_slides: List[Tuple[str, str, str]] = field(init=False)
    candidate_slides: List[Tuple[str, str, str]] = field(init=False)
    candidate_target_part: str = field(init=False)
    baseline_target_part: str = field(init=False)
    mapping: Dict[str, str] = field(default_factory=dict)
    replacements: Dict[str, bytes] = field(default_factory=dict)
    additions: Dict[str, bytes] = field(default_factory=dict)
    remove: Set[str] = field(default_factory=set)
    mapped_reused: List[Tuple[str, str]] = field(default_factory=list)
    mapped_cloned: List[Tuple[str, str]] = field(default_factory=list)
    queue: List[Tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.baseline_slides = _presentation_slides(self.baseline)
        self.candidate_slides = _presentation_slides(self.candidate)
        if len(self.baseline_slides) != len(self.candidate_slides):
            raise IncrementalReplaceError(
                "baseline and modified pptx.yaml export have different slide counts; "
                "incremental replacement refuses page insertion/deletion"
            )
        if self.target_index < 1 or self.target_index > len(self.baseline_slides):
            raise IncrementalReplaceError(
                f"page index must be between 1 and {len(self.baseline_slides)}"
            )
        self.baseline_target_part = self.baseline_slides[self.target_index - 1][0]
        self.candidate_target_part = self.candidate_slides[self.target_index - 1][0]

    def _allocate_clone(self, candidate_part: str) -> str:
        candidate_part = _normal_part_name(candidate_part)
        parent = posixpath.dirname(candidate_part)
        basename = posixpath.basename(candidate_part)
        stem, extension = posixpath.splitext(basename)
        occupied = (
            set(self.baseline.parts) | set(self.additions) | set(self.mapping.values())
        )
        for index in range(1, 10000):
            suffix = f".inc{index}"
            name = posixpath.join(parent, stem + suffix + extension)
            if name not in occupied:
                return name
        raise IncrementalReplaceError(
            f"cannot allocate an isolated part for {candidate_part}"
        )

    def _map_part(
        self, candidate_part: str, *, force_output: Optional[str] = None
    ) -> str:
        candidate_part = _normal_part_name(candidate_part)
        if candidate_part in self.mapping:
            mapped = self.mapping[candidate_part]
            if force_output is not None and mapped != _normal_part_name(force_output):
                raise IncrementalReplaceError(
                    f"candidate part {candidate_part} was mapped inconsistently"
                )
            return mapped
        if _is_forbidden_candidate_part(candidate_part, self.candidate_target_part):
            raise IncrementalReplaceError(
                "target page depends on a package-global or different slide part: "
                f"{candidate_part}"
            )
        if not self.candidate.has(candidate_part):
            raise IncrementalReplaceError(
                f"candidate relationship targets missing part: {candidate_part}"
            )

        if force_output is not None:
            output_part = _normal_part_name(force_output)
        elif self.candidate_target_part == candidate_part:
            output_part = self.baseline_target_part
        elif self.baseline.has(candidate_part) and _part_equivalent(
            self.candidate, candidate_part, self.baseline, candidate_part
        ):
            output_part = candidate_part
        elif self.baseline.has(candidate_part):
            output_part = self._allocate_clone(candidate_part)
        else:
            occupied = (
                set(self.baseline.parts)
                | set(self.additions)
                | set(self.mapping.values())
            )
            output_part = (
                candidate_part
                if candidate_part not in occupied
                else self._allocate_clone(candidate_part)
            )

        if (
            output_part in self.mapping.values()
            and self.mapping.get(candidate_part) != output_part
        ):
            raise IncrementalReplaceError(
                f"output part mapping collision: {output_part}"
            )
        self.mapping[candidate_part] = output_part
        self.queue.append((candidate_part, output_part))
        if (
            output_part == self.baseline_target_part
            and candidate_part == self.candidate_target_part
        ):
            # The selected slide is replaced in place, not counted as a clone.
            pass
        elif output_part == candidate_part and self.baseline.has(output_part):
            self.mapped_reused.append((candidate_part, output_part))
        else:
            self.mapped_cloned.append((candidate_part, output_part))
        return output_part

    def _rewrite_relationships(
        self,
        candidate_rels_part: str,
        output_rels_part: str,
        candidate_source_part: str,
        output_source_part: str,
    ) -> bytes:
        root = _parse_xml(self.candidate, candidate_rels_part)
        if root.tag != RELATIONSHIPS_TAG:
            raise IncrementalReplaceError(
                f"invalid candidate relationship root: {candidate_rels_part}"
            )
        seen_ids: Set[str] = set()
        for rel in root:
            if rel.tag != REL_TAG:
                raise IncrementalReplaceError(f"invalid child in {candidate_rels_part}")
            rel_id = rel.attrib.get("Id")
            if not rel_id or rel_id in seen_ids:
                raise IncrementalReplaceError(
                    f"duplicate relationship Id in {candidate_rels_part}"
                )
            seen_ids.add(rel_id)
            if _is_external_relationship(rel):
                continue
            target, fragment = resolve_relationship_target(
                candidate_source_part, rel.attrib["Target"]
            )
            output_target = self._map_part(target)
            rel.attrib["Target"] = relative_relationship_target(
                output_source_part, output_target, fragment
            )
        return _serialize_xml(root)

    def build(self) -> None:
        self._map_part(
            self.candidate_target_part,
            force_output=self.baseline_target_part,
        )
        while self.queue:
            candidate_part, output_part = self.queue.pop(0)
            candidate_data = self.candidate.get(candidate_part)
            output_rels = relationship_part_name(output_part)
            candidate_rels = relationship_part_name(candidate_part)

            if candidate_part == self.candidate_target_part or not (
                output_part in self.baseline.parts
                and _part_equivalent(
                    self.candidate, candidate_part, self.baseline, output_part
                )
            ):
                if output_part in self.baseline.parts:
                    self.replacements[output_part] = candidate_data
                else:
                    self.additions[output_part] = candidate_data

            if self.candidate.has(candidate_rels):
                rewritten = self._rewrite_relationships(
                    candidate_rels,
                    output_rels,
                    candidate_part,
                    output_part,
                )
                # An equivalent shared part already carries an equivalent
                # relationship part in the baseline.  Do not rewrite it just
                # because the candidate was traversed; this keeps all
                # non-target package state byte-stable as well as semantic.
                reused_shared = (
                    candidate_part != self.candidate_target_part
                    and output_part in self.baseline.parts
                    and _part_equivalent(
                        self.candidate, candidate_part, self.baseline, output_part
                    )
                )
                if not reused_shared:
                    if output_rels in self.baseline.parts:
                        self.replacements[output_rels] = rewritten
                    else:
                        self.additions[output_rels] = rewritten
            elif candidate_part == self.candidate_target_part and self.baseline.has(
                output_rels
            ):
                # A target page with no relationships must not retain old
                # images, notes, or chart links through its old .rels part.
                self.remove.add(output_rels)

        self._merge_content_types()

    def _merge_content_types(self) -> None:
        """Add content-type declarations for copied candidate parts."""

        baseline_root = _parse_xml(self.baseline, "[Content_Types].xml")
        candidate_root = _parse_xml(self.candidate, "[Content_Types].xml")
        baseline_overrides: Dict[str, ET.Element] = {
            child.attrib["PartName"]: child
            for child in baseline_root
            if child.tag == OVERRIDE_TAG and "PartName" in child.attrib
        }
        candidate_overrides: Dict[str, ET.Element] = {
            child.attrib["PartName"]: child
            for child in candidate_root
            if child.tag == OVERRIDE_TAG and "PartName" in child.attrib
        }
        baseline_defaults: Dict[str, str] = {
            child.attrib["Extension"].lower(): child.attrib["ContentType"]
            for child in baseline_root
            if child.tag == DEFAULT_TAG
            and "Extension" in child.attrib
            and "ContentType" in child.attrib
        }
        candidate_defaults: Dict[str, str] = {
            child.attrib["Extension"].lower(): child.attrib["ContentType"]
            for child in candidate_root
            if child.tag == DEFAULT_TAG
            and "Extension" in child.attrib
            and "ContentType" in child.attrib
        }

        changed = False
        for candidate_part, output_part in self.mapping.items():
            if output_part in self.baseline.parts and output_part not in self.additions:
                continue
            candidate_override = candidate_overrides.get("/" + candidate_part)
            if candidate_override is not None:
                part_name = "/" + output_part
                if part_name not in baseline_overrides:
                    child = ET.Element(OVERRIDE_TAG)
                    child.attrib["PartName"] = part_name
                    child.attrib["ContentType"] = candidate_override.attrib[
                        "ContentType"
                    ]
                    baseline_root.append(child)
                    baseline_overrides[part_name] = child
                    changed = True
                continue
            extension = posixpath.splitext(output_part)[1].lstrip(".").lower()
            if extension not in baseline_defaults:
                content_type = candidate_defaults.get(extension)
                if content_type is None:
                    raise IncrementalReplaceError(
                        f"candidate part {candidate_part} has no content-type declaration"
                    )
                child = ET.Element(DEFAULT_TAG)
                child.attrib["Extension"] = extension
                child.attrib["ContentType"] = content_type
                baseline_root.append(child)
                baseline_defaults[extension] = content_type
                changed = True
        if changed:
            self.replacements["[Content_Types].xml"] = _serialize_xml(baseline_root)

    def _closure(self, pkg: Package, slide_part: str) -> Set[str]:
        closure: Set[str] = set()
        queue = [slide_part]
        while queue:
            part = queue.pop(0)
            if part in closure:
                continue
            if not pkg.has(part):
                raise IncrementalReplaceError(
                    f"dependency closure references missing part: {part}"
                )
            closure.add(part)
            rels = relationship_part_name(part)
            if not pkg.has(rels):
                continue
            closure.add(rels)
            for rel in _relationship_elements(pkg, rels):
                if _is_external_relationship(rel):
                    continue
                target, _ = resolve_relationship_target(part, rel.attrib["Target"])
                queue.append(target)
        return closure

    def verify(self, output: Package) -> Dict[str, Any]:
        output_slides = _presentation_slides(output)
        if len(output_slides) != len(self.baseline_slides):
            raise IncrementalReplaceError(
                "output slide count changed during incremental replacement"
            )

        # The presentation index and every slide relationship are copied from
        # baseline.  Explicitly check them so an accidental global rewrite is
        # caught even if all slide XML parts happen to look similar.
        before_presentation = canonical_xml(self.baseline.get("ppt/presentation.xml"))
        after_presentation = canonical_xml(output.get("ppt/presentation.xml"))
        if before_presentation != after_presentation:
            raise IncrementalReplaceError(
                "presentation.xml changed; slide IDs/order are not stable"
            )
        before_presentation_rels = canonical_relationships(
            self.baseline.get("ppt/_rels/presentation.xml.rels")
        )
        after_presentation_rels = canonical_relationships(
            output.get("ppt/_rels/presentation.xml.rels")
        )
        if before_presentation_rels != after_presentation_rels:
            raise IncrementalReplaceError("presentation relationships changed")

        non_target: List[Dict[str, Any]] = []
        for index, (
            (before_part, before_id, before_rel),
            (after_part, after_id, after_rel),
        ) in enumerate(zip(self.baseline_slides, output_slides), start=1):
            if index == self.target_index:
                continue
            if (before_part, before_id, before_rel) != (
                after_part,
                after_id,
                after_rel,
            ):
                raise IncrementalReplaceError(
                    f"non-target slide {index} presentation identity changed"
                )
            before_closure = self._closure(self.baseline, before_part)
            closure_records: List[Dict[str, Any]] = []
            for part in sorted(before_closure):
                if not output.has(part):
                    raise IncrementalReplaceError(
                        f"non-target slide {index} lost associated part: {part}"
                    )
                before_hash = semantic_digest(part, self.baseline.get(part))
                after_hash = semantic_digest(part, output.get(part))
                if before_hash != after_hash:
                    raise IncrementalReplaceError(
                        f"non-target slide {index} associated part changed: {part}"
                    )
                closure_records.append(
                    {
                        "part": part,
                        "semanticHash": before_hash,
                        "rawHashBefore": raw_digest(self.baseline.get(part)),
                        "rawHashAfter": raw_digest(output.get(part)),
                    }
                )
            non_target.append(
                {
                    "pageIndex": index,
                    "slidePart": before_part,
                    "slideId": before_id,
                    "presentationRelationshipId": before_rel,
                    "slideSemanticHash": semantic_digest(
                        before_part, self.baseline.get(before_part)
                    ),
                    "slideRelsSemanticHash": semantic_digest(
                        relationship_part_name(before_part),
                        self.baseline.get(relationship_part_name(before_part)),
                    )
                    if self.baseline.has(relationship_part_name(before_part))
                    else None,
                    "associatedParts": closure_records,
                }
            )

        target_before = semantic_digest(
            self.baseline_target_part, self.baseline.get(self.baseline_target_part)
        )
        target_after = semantic_digest(
            self.baseline_target_part, output.get(self.baseline_target_part)
        )
        return {
            "verified": True,
            "pageIndex": self.target_index,
            "baselineSlidePart": self.baseline_target_part,
            "candidateSlidePart": self.candidate_target_part,
            "targetSemanticHashBefore": target_before,
            "targetSemanticHashAfter": target_after,
            "targetChanged": target_before != target_after,
            "reusedParts": sorted(self.mapped_reused),
            "clonedParts": sorted(self.mapped_cloned),
            "replacedParts": sorted(self.replacements),
            "removedParts": sorted(self.remove),
            "nonTargetSlides": non_target,
        }


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
    from .project import atomic_write

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
    from .project import find_manifest, image_objects, load_project
    from .validation import safe_path

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
        from .project import export_project

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
