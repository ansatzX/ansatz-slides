"""Real optional local TeX integration; no mocked success of a math renderer."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import struct

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('equation_helper', ROOT / 'skills/ansatz-slide/scripts/render_equation.py')
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


@unittest.skipUnless(shutil.which('pdflatex') and shutil.which('pdftocairo'), 'optional pdfLaTeX/Poppler unavailable')
class EquationHelperTests(unittest.TestCase):
    def test_real_math_aspect_ratio_and_failure_preserves_asset(self):
        scratch = ROOT / 'tmp/test-tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            expression, output = root/'input.math.txt', root/'model.png'
            body = r'\begin{aligned}r&=\sqrt{x^2+y^2}\\\hat H&=\frac{\hbar\omega}{2}\end{aligned}'
            expression.write_text(body)
            result = HELPER.render(expression, output, [20, 30, 300, 100])
            data = output.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            dimensions = struct.unpack('>II', data[16:24])
            self.assertEqual(max(dimensions), 1200)
            self.assertIn(body, output.with_suffix('.source.tex').read_text())
            x, y, w, h = result['bounds']
            self.assertAlmostEqual(w/h, result['pixels'][0]/result['pixels'][1])
            self.assertGreaterEqual(x, 20)
            self.assertGreaterEqual(y, 30)
            self.assertLessEqual(x+w, 320.000001)
            self.assertLessEqual(y+h, 130.000001)
            before = output.read_bytes(), output.with_suffix('.source.tex').read_bytes()
            expression.write_text(r'\notARealCommand{x}')
            with self.assertRaises(RuntimeError):
                HELPER.render(expression, output, force=True)
            self.assertEqual(before, (output.read_bytes(), output.with_suffix('.source.tex').read_bytes()))
            self.assertEqual([], list(root.glob('.equation-*')))

    def test_existing_output_requires_explicit_replacement(self):
        scratch = ROOT/'tmp/test-tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder); expression = root/'input.txt'; output = root/'eq.png'
            expression.write_text('x'); output.write_text('baseline')
            with self.assertRaises(FileExistsError):
                HELPER.render(expression, output)
            self.assertEqual('baseline', output.read_text())

    def test_second_publish_failure_restores_png_and_source_pair(self):
        from unittest.mock import patch
        scratch=ROOT/'tmp/test-tmp';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root=Path(folder);expression=root/'input.txt';output=root/'eq.png'
            expression.write_text('x');HELPER.render(expression,output)
            before={p:p.read_bytes() for p in [output,output.with_suffix('.source.tex')]}
            expression.write_text('y^2');original=HELPER.os.link
            def fail(src,dst,*args,**kwargs):
                if Path(src).name=='equation.png' and Path(dst)==output:
                    raise OSError('PNG publication failure')
                return original(src,dst,*args,**kwargs)
            with patch.object(HELPER.os,'link',fail):
                with self.assertRaisesRegex(RuntimeError,'PNG publication failure'):
                    HELPER.render(expression,output,force=True)
            for p,data in before.items():self.assertEqual(data,p.read_bytes())
            self.assertTrue(list((root/'.ansatz-equations').glob('*/eq.source.tex.previous')))

    def test_late_output_creation_is_preserved_without_force(self):
        from unittest.mock import patch
        scratch=ROOT/'tmp/test-tmp';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root=Path(folder);expression=root/'input.txt';output=root/'eq.png'
            expression.write_text('x');original=HELPER.subprocess.run;injected=False
            def race(*args,**kwargs):
                nonlocal injected
                result=original(*args,**kwargs)
                if not injected:output.write_bytes(b'external output');injected=True
                return result
            with patch.object(HELPER.subprocess,'run',race):
                with self.assertRaisesRegex(RuntimeError,'changed during rendering'):
                    HELPER.render(expression,output)
            self.assertEqual(b'external output',output.read_bytes())
            self.assertFalse(output.with_suffix('.source.tex').exists())
