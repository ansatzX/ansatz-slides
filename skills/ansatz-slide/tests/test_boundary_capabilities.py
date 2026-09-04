from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = REPO_ROOT / "tmp"
CLI = REPO_ROOT / "bin" / "ansatz-slide.js"
FIXTURE = Path(__file__).parent / "fixtures" / "boundary-capabilities"

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
K_NS = "https://kimi-design.msh.team/pptd/2026"


def _tag(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def _chart_values(root: ET.Element, container: str) -> list[float]:
    return [
        float(node.text)
        for node in root.findall(
            f".//{_tag(C_NS, container)}//{_tag(C_NS, 'v')}"
        )
        if node.text is not None
    ]


class BoundaryCapabilityTests(unittest.TestCase):
    def _export_fixture(self, output: Path) -> subprocess.CompletedProcess[str]:
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required by the core exporter")
        env = os.environ.copy()
        env["TMPDIR"] = str(TMP_ROOT / "test-tmp")
        return subprocess.run(
            [node, str(CLI), "export", str(FIXTURE), "--output", str(output)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_exported_fixture_retains_chart_and_animation_semantics(self):
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="boundary-capabilities-", dir=TMP_ROOT
        ) as temp_name:
            output = Path(temp_name) / "boundary-capabilities.pptx"
            result = self._export_fixture(output)
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue(output.is_file())

            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                chart_parts = sorted(
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/charts/chart") and name.endswith(".xml")
                )
                self.assertEqual(len(chart_parts), 2)
                charts = [ET.fromstring(archive.read(name)) for name in chart_parts]

                scatter = next(
                    root
                    for root in charts
                    if root.find(f".//{_tag(C_NS, 'scatterChart')}") is not None
                )
                bubble = next(
                    root
                    for root in charts
                    if root.find(f".//{_tag(C_NS, 'bubbleChart')}") is not None
                )

                # A scatter/bubble x axis must be a value axis.  A categorical
                # fallback can look plausible while changing chart semantics.
                for root in (scatter, bubble):
                    self.assertEqual(len(root.findall(f".//{_tag(C_NS, 'valAx')}")), 2)
                    self.assertEqual(len(root.findall(f".//{_tag(C_NS, 'catAx')}")), 0)

                self.assertEqual(_chart_values(scatter, "xVal"), [1, 3, 6, 9])
                self.assertEqual(_chart_values(scatter, "yVal"), [12, 38, 62, 92])
                marker = scatter.find(f".//{_tag(C_NS, 'marker')}")
                self.assertIsNotNone(marker)
                self.assertEqual(marker.find(_tag(C_NS, "symbol")).get("val"), "diamond")
                self.assertEqual(marker.find(_tag(C_NS, "size")).get("val"), "14")

                self.assertEqual(_chart_values(bubble, "xVal"), [1, 3, 6, 9])
                self.assertEqual(_chart_values(bubble, "yVal"), [18, 42, 67, 88])
                bubble_sizes = _chart_values(bubble, "bubbleSize")
                self.assertEqual(len(bubble_sizes), 4)
                self.assertEqual(bubble_sizes, sorted(bubble_sizes))
                self.assertTrue(all(value > 0 for value in bubble_sizes))

                slide = ET.fromstring(archive.read("ppt/slides/slide2.xml"))
                root_children = [child.tag.rsplit("}", 1)[-1] for child in slide]
                self.assertEqual(
                    root_children,
                    ["cSld", "clrMapOvr", "transition", "timing"],
                )
                self.assertIsNotNone(
                    slide.find(
                        f"./{_tag(P_NS, 'transition')}/{_tag(P_NS, 'fade')}"
                    )
                )
                timing = slide.find(_tag(P_NS, "timing"))
                self.assertIsNotNone(timing)
                for node_name in (
                    "animEffect",
                    "anim",
                    "animScale",
                    "animClr",
                    "animMotion",
                    "bldLst",
                ):
                    self.assertIsNotNone(
                        timing.find(f".//{_tag(P_NS, node_name)}"), node_name
                    )

                durations = {
                    int(node.get("dur"))
                    for node in timing.findall(f".//{_tag(P_NS, 'cTn')}")
                    if (node.get("dur") or "").isdigit()
                }
                self.assertTrue({400, 500, 600, 800, 900}.issubset(durations))

                shape_ids = {}
                for shape in slide.findall(f".//{_tag(P_NS, 'sp')}"):
                    props = shape.find(
                        f"./{_tag(P_NS, 'nvSpPr')}/{_tag(P_NS, 'cNvPr')}"
                    )
                    if props is not None:
                        shape_ids[props.get("name")] = props.get("id")
                animated_spids = {
                    node.get("spid")
                    for node in timing.findall(f".//{_tag(P_NS, 'spTgt')}")
                }
                for name in ("anim-title", "anim-panel", "anim-icon", "anim-line"):
                    self.assertIn(shape_ids[name], animated_spids)

                # Icons currently survive as a private extension plus a generic
                # editable fallback shape.  This proves serialization, but it
                # deliberately does not claim a native PowerPoint vector icon.
                icon_shape = next(
                    shape
                    for shape in slide.findall(f".//{_tag(P_NS, 'sp')}")
                    if (
                        shape.find(
                            f"./{_tag(P_NS, 'nvSpPr')}/{_tag(P_NS, 'cNvPr')}"
                        ).get("name")
                        == "anim-icon"
                    )
                )
                icon_ext = icon_shape.find(f".//{_tag(K_NS, 'icon')}")
                self.assertIsNotNone(icon_ext)
                encoded = icon_ext.text or ""
                encoded += "=" * (-len(encoded) % 4)
                payload = json.loads(base64.urlsafe_b64decode(encoded))
                self.assertEqual(payload, {"iconName": "fas:circle-play"})
                fallback = icon_shape.find(
                    f"./{_tag(P_NS, 'spPr')}/{_tag(A_NS, 'prstGeom')}"
                )
                self.assertIsNotNone(fallback)
                self.assertEqual(fallback.get("prst"), "ellipse")


if __name__ == "__main__":
    unittest.main()
