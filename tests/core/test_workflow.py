"""End-to-end file workflow and failure/preservation boundaries.

Scratch output is under ./tmp (or explicit ANSATZ_SLIDE_TEST_TMP), never system /tmp.
"""

import base64
import copy
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ansatz_slide.cli import main
from ansatz_slide.incremental import (
    IncrementalPatcher,
    IncrementalReplaceError,
    replace_from_project,
)
from ansatz_slide.package import inspect_pptx
from ansatz_slide.project import (
    export_project,
    load_project,
    parse_document,
    resolve_images,
)
from ansatz_slide.validation import ValidationError, validate_project
if __package__:
    from .test_regression import fingerprints
else:
    from test_regression import fingerprints

FIXTURES = Path(__file__).with_name("fixtures")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get("ANSATZ_SLIDE_TEST_TMP", Path.cwd() / "tmp"))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="python-workflow-", dir=scratch
        )
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def project(self):
        root = self.root / "deck"
        root.mkdir()
        (root / "pptx.yaml").write_text(
            json.dumps(
                {"version": "v2", "size": [960, 540], "pages": ["1.page.yaml", "2.page.yaml"]}
            )
        )
        for i in (1, 2):
            (root / f"{i}.page.yaml").write_text(
                json.dumps(
                    {
                        "elements": [
                            {
                                "elementId": "title",
                                "elementType": "text",
                                "bounds": [20, 20, 400, 100],
                                "content": {"text": f"Page {i}"},
                            }
                        ]
                    }
                )
            )
        return root

    def test_seven_file_projects_match_recorded_original_parts(self):
        expected = json.loads((FIXTURES / "workflow/expected.json").read_text())
        for name, wanted in expected.items():
            with self.subTest(project=name):
                path = self.root / (name + ".pptx")
                # Any hidden delegation to an external runtime is a test failure.
                with (
                    # Preserve frozen serializer fingerprints for old layout
                    # fixtures; live gate/preservation tests run without this mock.
                    patch('ansatz_slide.occupancy.require_pages',return_value=[]),
                    patch(
                        "subprocess.Popen",
                        side_effect=AssertionError("external process"),
                    ),
                    patch("os.system", side_effect=AssertionError("shell")),
                ):
                    export_project(
                        FIXTURES / "workflow" / name, path, allow_remote=False
                    )
                self.assertEqual(fingerprints(path.read_bytes()), wanted)

    def test_recorded_validator_decisions(self):
        for i, case in enumerate(
            json.loads((FIXTURES / "validator-decisions.json").read_text())
        ):
            with self.subTest(case=i):
                value = case["input"]
                if case["ok"]:
                    validate_project(
                        value["manifest"],
                        [p["data"] for p in value["pages"]],
                        check_files=False,
                    )
                else:
                    with self.assertRaises(ValidationError):
                        validate_project(
                            value["manifest"],
                            [p["data"] for p in value["pages"]],
                            check_files=False,
                        )

    def test_json_cli_and_incremental_need_no_optional_imports_or_processes(self):
        root = self.project()
        output = self.root / "baseline.pptx"
        import builtins

        original = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"yaml", "PIL", "websocket", "subprocess"}:
                raise AssertionError("forbidden runtime import: " + name)
            return original(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=guarded),
            redirect_stdout(io.StringIO()),
        ):
            for argv in [
                ["validate", str(root)],
                ["export", str(root), "-o", str(output), "--offline"],
                ["inspect", str(output)],
            ]:
                self.assertEqual(main(argv), 0)
            page = json.loads((root / "2.page.yaml").read_text())
            page["elements"][0]["content"]["text"] = "Changed target"
            (root / "2.page.yaml").write_text(json.dumps(page))
            updated = self.root / "updated.pptx"
            self.assertEqual(
                main(
                    [
                        "replace-page",
                        "--baseline",
                        str(output),
                        "--project",
                        str(root),
                        "--page",
                        "2",
                        "-o",
                        str(updated),
                    ]
                ),
                0,
            )
        before = fingerprints(output.read_bytes())
        after = fingerprints(updated.read_bytes())
        self.assertEqual(
            before["ppt/slides/slide1.xml"], after["ppt/slides/slide1.xml"]
        )
        self.assertNotEqual(
            before["ppt/slides/slide2.xml"], after["ppt/slides/slide2.xml"]
        )

    def test_validation_failure_preserves_existing_output(self):
        root = self.project()
        out = self.root / "out.pptx"
        out.write_bytes(b"old output")
        page = json.loads((root / "1.page.yaml").read_text())
        page["elements"][0]["unexpected"] = 1
        (root / "1.page.yaml").write_text(json.dumps(page))
        with self.assertRaises(ValidationError):
            export_project(root, out, force=True)
        self.assertEqual(out.read_bytes(), b"old output")
        self.assertFalse(list(self.root.glob("*.partial")))

    def test_no_clobber_and_source_protection(self):
        root = self.project()
        out = self.root / "out.pptx"
        out.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            export_project(root, out)
        original = (root / "1.page.yaml").read_bytes()
        with self.assertRaises(ValidationError):
            export_project(root, root / "1.page.yaml", force=True)
        self.assertEqual((root / "1.page.yaml").read_bytes(), original)

    def test_incremental_verification_failure_keeps_existing_delivery(self):
        root = self.project()
        baseline = self.root / "baseline.pptx"
        export_project(root, baseline)
        output = self.root / "previous.pptx"
        output.write_bytes(b"previous delivery")
        with patch.object(
            IncrementalPatcher,
            "verify",
            side_effect=IncrementalReplaceError("simulated verification mismatch"),
        ):
            with self.assertRaises(IncrementalReplaceError):
                replace_from_project(baseline, root, 2, output, force=True)
        self.assertEqual(output.read_bytes(), b"previous delivery")
        before = baseline.read_bytes()
        with self.assertRaises(IncrementalReplaceError):
            replace_from_project(baseline, root, 2, baseline, force=True)
        self.assertEqual(baseline.read_bytes(), before)

    def test_paths_and_symlink_escapes_rejected_before_read(self):
        root = self.project()
        manifest = json.loads((root / "pptx.yaml").read_text())
        outside = self.root / "outside.page.yaml"
        outside.write_text('{"elements":[]}')
        (root / "escape.page.yaml").symlink_to(outside)
        for path in [
            "../outside.page.yaml",
            "/absolute.page.yaml",
            "C:\\outside.page.yaml",
            "escape.page.yaml",
        ]:
            with self.subTest(path=path):
                manifest["pages"] = [path]
                (root / "pptx.yaml").write_text(json.dumps(manifest))
                with self.assertRaises(ValidationError):
                    load_project(root)

    def test_yaml_12_scalars_duplicates_and_recursive_alias(self):
        self.assertEqual(
            parse_document(
                "text: on\nother: no\nn: 012\nx: 1e3\nb: true\ndate: 2026-09-07", "test"
            ),
            {
                "text": "on",
                "other": "no",
                "n": 12,
                "x": 1000.0,
                "b": True,
                "date": "2026-09-07",
            },
        )
        for source in [
            "x: 1\nx: 2",
            '{"x":1,"x":2}',
            "x: &x [*x]",
            "x: !!python/object:Foo {}",
            "x: {<<: {a: 1}}",
        ]:
            with self.subTest(source=source), self.assertRaises(ValidationError):
                parse_document(source, "bad")

    def test_resources_all_locations_aliases_dedup_and_offline(self):
        data = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>'
        (self.root / "asset.svg").write_bytes(data)
        fill = {"type": "image", "src": "asset.svg"}
        pptd = {
            "pages": [
                {
                    "background": fill,
                    "elements": [
                        {"elementType": "shape", "fill": fill},
                        {"elementType": "image", "src": "asset.svg"},
                        {
                            "elementType": "image",
                            "src": "data:image/svg+xml;base64,"
                            + base64.b64encode(data).decode(),
                        },
                    ],
                }
            ]
        }
        images = resolve_images(pptd, self.root, allow_remote=False)
        self.assertEqual(len(images), 2)
        self.assertEqual(set(images.values()), {data})
        self.assertEqual(
            pptd["pages"][0]["elements"][0]["fill"]["src"],
            pptd["pages"][0]["background"]["src"],
        )
        remote = {
            "pages": [
                {
                    "elements": [
                        {
                            "elementType": "image",
                            "src": "https://example.invalid/image.png",
                        }
                    ]
                }
            ]
        }
        with patch(
            "ansatz_slide.project.urlopen", side_effect=AssertionError("must not fetch")
        ):
            with self.assertRaises(ValidationError):
                resolve_images(remote, self.root, allow_remote=False)

    def test_unknown_and_bad_nested_fields_rejected(self):
        case = json.loads((FIXTURES / "validator-decisions.json").read_text())[0][
            "input"
        ]
        # Every element type and nested supported object rejects unknown fields.
        targets = []

        def walk(value, path):
            if isinstance(value, dict):
                targets.append(path)
                for k, x in value.items():
                    walk(x, path + [k])
            elif isinstance(value, list):
                for i, x in enumerate(value):
                    walk(x, path + [i])

        for i, e in enumerate(case["pages"][0]["data"]["elements"]):
            walk(e, ["pages", 0, "data", "elements", i])
        for path in targets:
            sample = copy.deepcopy(case)
            target = sample
            for part in path:
                target = target[part]
            target["__unsupported__"] = True
            with self.subTest(path=path), self.assertRaises(ValidationError):
                validate_project(
                    sample["manifest"],
                    [p["data"] for p in sample["pages"]],
                    check_files=False,
                )
        for invalid in [True, float("nan"), float("inf"), -1, 0]:
            sample = copy.deepcopy(case)
            sample["manifest"]["size"][0] = invalid
            with self.subTest(size=invalid), self.assertRaises(ValidationError):
                validate_project(
                    sample["manifest"],
                    [p["data"] for p in sample["pages"]],
                    check_files=False,
                )

    def test_inspector_rejects_broken_relationships(self):
        root = self.project()
        out = self.root / "out.pptx"
        export_project(root, out)
        buf = io.BytesIO()
        with zipfile.ZipFile(out) as source, zipfile.ZipFile(buf, "w") as dest:
            for name in source.namelist():
                data = source.read(name)
                if name == "ppt/_rels/presentation.xml.rels":
                    data = data.replace(b"slides/slide1.xml", b"slides/missing.xml")
                dest.writestr(name, data)
        with self.assertRaisesRegex(ValueError, "Broken relationship"):
            inspect_pptx(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
