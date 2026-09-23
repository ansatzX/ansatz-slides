"""Keep the small, model-facing authoring example executable against the writer."""
import re
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/ansatz-slide'


class AuthoringStartTests(unittest.TestCase):
    def test_published_starter_exports_expected_native_objects(self):
        content = (SKILL/'reference/authoring-start.md').read_text()
        blocks = re.findall(r'```yaml\n(.*?)\n```', content, re.S)
        self.assertEqual(len(blocks), 2)
        manifest, page = [yaml.safe_load(block) for block in blocks]
        scratch = ROOT/'tmp'; scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='authoring-start-', dir=scratch) as name:
            project = Path(name)
            (project/'settings.yaml').write_text(blocks[0])
            (project/'first.page.yaml').write_text(blocks[1])
            created = subprocess.run([sys.executable, str(SKILL/'scripts/ansatz_slide.py'), 'deck', 'create',
                                      str(project), '--settings', str(project/'settings.yaml'), '--content', str(project/'first.page.yaml')],
                                     capture_output=True, text=True, timeout=60)
            self.assertEqual(created.returncode, 0, created.stdout+created.stderr)
            output = project/'starter.pptx'
            result = subprocess.run([sys.executable, str(SKILL/'scripts/ansatz_slide.py'), 'export',
                                     str(project), '-o', str(output)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            with zipfile.ZipFile(output) as package:
                self.assertIsNone(package.testzip())
                xml = ET.fromstring(package.read('ppt/slides/slide1.xml'))
                ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
                      'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
                text = ''.join(n.text or '' for n in xml.findall('.//a:t', ns))
                for element in page['elements']:
                    if element['elementType']=='text':
                        self.assertIn(element['content']['text'], text)
                self.assertEqual(len(xml.findall('.//p:sp', ns)), 4)
                self.assertEqual(len(xml.findall('.//p:pic', ns)), 0)
                self.assertIsNotNone(xml.find('p:transition/p:fade', ns))


if __name__=='__main__':
    unittest.main()
