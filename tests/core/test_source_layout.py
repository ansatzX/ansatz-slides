"""Keep maintained Python modules readable after formatting and regrouping."""

from pathlib import Path
import unittest


class SourceLayoutTests(unittest.TestCase):
    def test_python_files_do_not_exceed_500_lines(self):
        root = Path(__file__).resolve().parents[2]
        folders = (
            "src/ansatz_slide",
            "scripts",
            "skills/ansatz-slide/scripts",
            "tests",
        )
        oversized = []
        for folder in folders:
            for path in (root / folder).rglob("*.py"):
                lines = len(path.read_text(encoding="utf-8").splitlines())
                if lines > 500:
                    oversized.append((str(path.relative_to(root)), lines))
        self.assertEqual(
            [], oversized, "Split modules by responsibility; do not compress lines."
        )
