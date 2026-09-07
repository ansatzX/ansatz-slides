"""Typed YAML source filenames and explicit failure on retired suffixes."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ansatz_slide.project import find_manifest, export_project
from ansatz_slide.validation import ValidationError
if __package__:
    from .test_regression import fingerprints
else:
    from test_regression import fingerprints

class YamlPathsTests(unittest.TestCase):
    def test_typed_yaml_export_discovery_and_retired_names(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / 'tmp') as tmp:
            root=Path(tmp)
            (root/'01.page.yaml').write_text('elements: []\n')
            (root/'config.yaml').write_text('pages: [irrelevant]\n')
            text='version: v2\nsize: [960, 540]\npages: [01.page.yaml]\n'
            manifest=root/'pptx.yaml';manifest.write_text(text)
            self.assertEqual(find_manifest(root),manifest)
            export_project(root, root/'one.pptx')
            manifest.rename(root/'talk.pptx.yaml')
            export_project(root,root/'named.pptx')
            self.assertEqual(fingerprints((root/'one.pptx').read_bytes()),fingerprints((root/'named.pptx').read_bytes()))
            manifest.write_text(text)
            with self.assertRaisesRegex(ValidationError,'exactly one'):find_manifest(root)
            for name in ('deck.pptd','deck.yaml','deck.json','01.page.yaml'):
                with self.subTest(name=name):
                    path=root/name
                    if not path.exists():path.write_text(text)
                    with self.assertRaises(ValidationError):find_manifest(path)
            for name in ('01.page','01.yaml'):
                (root/name).write_text('elements: []\n')
                manifest.write_text(text.replace('01.page.yaml',name))
                with self.assertRaisesRegex(ValidationError,'Page source must'):
                    export_project(manifest,root/'bad.pptx')
            self.assertFalse((root/'bad.pptx').exists())

if __name__ == '__main__': unittest.main()
