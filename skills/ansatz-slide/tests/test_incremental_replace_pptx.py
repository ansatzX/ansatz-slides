from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = REPO_ROOT / "tmp"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "incremental_replace_pptx.py"
SPEC = importlib.util.spec_from_file_location("incremental_replace_pptx", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _presentation_xml() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId3"/>
    <p:sldId id="257" r:id="rId4"/>
    <p:sldId id="258" r:id="rId5"/>
  </p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="custom"/>
</p:presentation>
'''.encode()


def _presentation_rels() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide3.xml"/>
</Relationships>
'''.encode()


def _slide_xml(label: str, image_rel_id: str = "rId2") -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="100000" y="100000"/><a:ext cx="1000000" cy="300000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>
        <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="2400"/><a:t>{label}</a:t></a:r><a:endParaRPr sz="2400"/></a:p></p:txBody>
      </p:sp>
      <p:pic>
        <p:nvPicPr><p:cNvPr id="3" name="image"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="{image_rel_id}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="1200000" y="100000"/><a:ext cx="1000000" cy="1000000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
'''.encode()


def _slide_rels(image_name: str, *, dangerous_global: bool = False) -> bytes:
    extra = ""
    if dangerous_global:
        extra = (
            '<Relationship Id="rId3" '
            'Type="http://example.test/relationships/global" '
            'Target="../presentation.xml"/>'
        )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{image_name}"/>
  {extra}
</Relationships>
'''.encode()


def _content_types() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CT_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>
  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slides/slide3.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
</Types>
'''.encode()


def _make_package(path: Path, *, candidate: bool, dangerous_global: bool = False) -> None:
    """Create a tiny, valid-enough OOXML package without external libraries."""

    shared = b"baseline-shared-image"
    other = b"candidate-shared-image" if candidate else b"baseline-other-image"
    parts = {
        "[Content_Types].xml": _content_types(),
        "_rels/.rels": f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>'''.encode(),
        "ppt/presentation.xml": _presentation_xml(),
        "ppt/_rels/presentation.xml.rels": _presentation_rels(),
        "ppt/theme/theme1.xml": f'<a:theme xmlns:a="{A_NS}" name="test"><a:themeElements/></a:theme>'.encode(),
        "ppt/slideMasters/slideMaster1.xml": f'<p:sldMaster xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree/></p:cSld></p:sldMaster>'.encode(),
        "ppt/slideLayouts/slideLayout1.xml": f'<p:sldLayout xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree/></p:cSld></p:sldLayout>'.encode(),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>'''.encode(),
        "ppt/slides/slide1.xml": _slide_xml("Slide one"),
        "ppt/slides/slide2.xml": _slide_xml("New middle slide" if candidate else "Old middle slide"),
        "ppt/slides/slide3.xml": _slide_xml("Slide three"),
        "ppt/slides/_rels/slide1.xml.rels": _slide_rels("image1.png"),
        "ppt/slides/_rels/slide2.xml.rels": _slide_rels("image2.png", dangerous_global=dangerous_global),
        "ppt/slides/_rels/slide3.xml.rels": _slide_rels("image2.png"),
        # In the candidate, image2 is both the target image and a candidate
        # shared image.  Its path collides with baseline slide 3's image2,
        # forcing the patcher to isolate it as image2.inc1.png.
        "ppt/media/image1.png": shared,
        "ppt/media/image2.png": other,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


class IncrementalReplaceTests(unittest.TestCase):
    def _tempdir(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="incremental-unittest-", dir=str(TMP_ROOT))

    def test_middle_page_replacement_preserves_non_target_semantics_and_isolates_media(self):
        with self._tempdir() as temp_name:
            root = Path(temp_name)
            baseline_path = root / "baseline.pptx"
            candidate_path = root / "candidate.pptx"
            output_path = root / "incremental.pptx"
            _make_package(baseline_path, candidate=False)
            _make_package(candidate_path, candidate=True)

            report = MODULE.replace_from_candidate(
                baseline_path,
                candidate_path,
                page_index=2,
                output_path=output_path,
            )

            self.assertTrue(report["verified"])
            self.assertTrue(report["targetChanged"])
            self.assertEqual(report["pageIndex"], 2)
            self.assertEqual(report["baselineSlidePart"], "ppt/slides/slide2.xml")
            self.assertEqual(
                report["replacedParts"],
                ["ppt/slides/_rels/slide2.xml.rels", "ppt/slides/slide2.xml"],
            )
            self.assertIn(
                ("ppt/media/image2.png", "ppt/media/image2.inc1.png"),
                report["clonedParts"],
            )

            baseline = MODULE.Package.open(baseline_path)
            output = MODULE.Package.open(output_path)
            self.assertIsNone(zipfile.ZipFile(output_path).testzip())

            before_slides = MODULE._presentation_slides(baseline)
            after_slides = MODULE._presentation_slides(output)
            self.assertEqual(before_slides, after_slides)
            for page_index in (1, 3):
                before_part = before_slides[page_index - 1][0]
                after_part = after_slides[page_index - 1][0]
                self.assertEqual(
                    MODULE.semantic_digest(before_part, baseline.get(before_part)),
                    MODULE.semantic_digest(after_part, output.get(after_part)),
                )
                for associated in MODULE.IncrementalPatcher(
                    baseline, MODULE.Package.open(candidate_path), 2
                )._closure(baseline, before_part):
                    self.assertEqual(
                        MODULE.semantic_digest(associated, baseline.get(associated)),
                        MODULE.semantic_digest(associated, output.get(associated)),
                    )

            self.assertNotEqual(
                MODULE.semantic_digest("ppt/slides/slide2.xml", baseline.get("ppt/slides/slide2.xml")),
                MODULE.semantic_digest("ppt/slides/slide2.xml", output.get("ppt/slides/slide2.xml")),
            )
            self.assertEqual(output.get("ppt/media/image2.png"), b"baseline-other-image")
            self.assertEqual(output.get("ppt/media/image2.inc1.png"), b"candidate-shared-image")
            target_rels = output.get("ppt/slides/_rels/slide2.xml.rels").decode()
            self.assertIn("../media/image2.inc1.png", target_rels)
            self.assertNotIn("../media/image2.png", target_rels)

    def test_target_dependency_on_presentation_part_is_rejected(self):
        with self._tempdir() as temp_name:
            root = Path(temp_name)
            baseline_path = root / "baseline.pptx"
            candidate_path = root / "dangerous-candidate.pptx"
            output_path = root / "must-not-exist.pptx"
            _make_package(baseline_path, candidate=False)
            _make_package(candidate_path, candidate=True, dangerous_global=True)

            with self.assertRaisesRegex(
                MODULE.IncrementalReplaceError,
                "package-global or different slide part",
            ):
                MODULE.replace_from_candidate(
                    baseline_path,
                    candidate_path,
                    page_index=2,
                    output_path=output_path,
                )
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
