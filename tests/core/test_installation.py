"""Distribution tests exercise the installed skill, not the checkout imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ansatz_slide.installation import install_skill


class InstallationTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / 'tmp'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch, prefix='skill-install-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_installed_skill_exports_without_checkout_node_or_site_packages(self):
        destination = Path(install_skill(self.root / 'skills')['destination'])
        self.assertFalse((destination / 'editor').exists())
        self.assertFalse((destination / 'scripts/local-export').exists())
        self.assertFalse(list(destination.rglob('*.wasm')))
        self.assertTrue((destination / 'uv.lock').is_file())
        project = self.root / 'project'
        project.mkdir()
        (project / 'pptx.yaml').write_text(json.dumps({'version': 'v2', 'size': [960, 540], 'pages': ['01.page.yaml']}))
        (project / '01.page.yaml').write_text(json.dumps({'pageType': 'content', 'elements': []}))
        command = [sys.executable, '-S', str(destination / 'scripts/ansatz_slide.py')]
        env = {**os.environ, 'PATH': '/nonexistent', 'PYTHONPATH': '', 'PYTHONNOUSERSITE': '1'}
        output = self.root / 'result.pptx'
        for args in [['validate', str(project)], ['export', str(project), '-o', str(output), '--offline'], ['inspect', str(output)]]:
            result = subprocess.run(command + args, cwd=self.root, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)

    def test_existing_skill_requires_force_and_failed_staging_preserves_it(self):
        destination = Path(install_skill(self.root)['destination'])
        marker = destination / 'local-note.txt'
        marker.write_text('preserve me')
        with self.assertRaises(FileExistsError):
            install_skill(self.root)
        with patch('ansatz_slide.installation.shutil.copytree', side_effect=OSError('copy failed')):
            with self.assertRaises(OSError):
                install_skill(self.root, force=True)
        self.assertEqual(marker.read_text(), 'preserve me')
        install_skill(self.root, force=True)
        self.assertFalse(marker.exists())
        self.assertTrue((destination / 'SKILL.md').is_file())

    def test_force_refuses_to_replace_executing_source(self):
        source = Path(__file__).resolve().parents[2] / 'src/ansatz_slide'
        (self.root / 'ansatz-slide').symlink_to(source, target_is_directory=True)
        with self.assertRaises(ValueError):
            install_skill(self.root, force=True)
        self.assertTrue((source / 'cli.py').is_file())
        with self.assertRaises(ValueError):
            install_skill(source / 'nested-skills', force=True)
        self.assertFalse((source / 'nested-skills').exists())
