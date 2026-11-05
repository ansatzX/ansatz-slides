"""目标页面及依赖闭包的移植、共享资源隔离与非目标保护。"""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .support import (
    DEFAULT_TAG,
    OVERRIDE_TAG,
    REL_TAG,
    RELATIONSHIPS_TAG,
    IncrementalReplaceError,
    Package,
    _is_external_relationship,
    _is_forbidden_candidate_part,
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
)


@dataclass
class IncrementalPatcher:
    """构建目标页依赖闭包，同时保持包级身份不变。

    候选页若依赖包全局部件或其他页面则拒绝。相同的共享部件可以复用；不同
    的依赖会分配隔离部件名，避免影响基线中的其他页面。
    """

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

        # 目标页沿用基线中的原路径。可达共享部件仅在语义相同时复用；内容
        # 不同时必须克隆，避免非目标页面读到候选稿中的状态。
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
        """部件映射后重写内部关系目标，外部 URL 保持原样。"""
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
        """从选定页面遍历依赖，生成需要的包内改动。"""
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
        """检查页面身份稳定性，以及非目标依赖闭包的语义哈希。

        这只证明所枚举 OOXML 依赖闭包在包级保持；不能证明演示软件中的视觉等价。
        """
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
