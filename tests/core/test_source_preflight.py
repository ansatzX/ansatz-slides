"""Source issues must be found without producing a presentation or using Office."""
import base64
import copy
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from ansatz_slide.cli import main
from ansatz_slide.preflight import check
from ansatz_slide.project import export_project, load_project

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP9sAAAAASUVORK5CYII=')


def text(ident, value, bounds):
    return {'elementId': ident, 'elementType': 'text', 'bounds': bounds,
            'content': {'text': value, 'fontSize': 20, 'fontFamily': 'Arial'}}


class SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[2] / 'tmp/test-tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = self.root / 'future-project'
        self.inputs = self.root / 'inputs'
        self.inputs.mkdir()
        self.settings = self.inputs / 'settings.yaml'
        self.settings.write_text(json.dumps({'version': 'v2', 'size': [960, 540]}))
        self.plan = self.inputs / 'pages.json'
        self.plan.write_text(json.dumps(['1.page.yaml']))
        self.bad = {'allowedOverlaps': [{'elements': ['card', 'body'], 'reason': 'Text in its panel'}],
                    'elements': [text('title', '阈值相关指标', [28, 4, 904, 40]),
                                 {'elementId': 'card', 'elementType': 'shape', 'shapeName': 'rect',
                                  'bounds': [36, 100, 280, 320]},
                                 text('body', '公式 kr、σopt 与 τS1', [48, 120, 250, 70]),
                                 {'elementId': 'eq', 'elementType': 'image', 'bounds': [500, 100, 200, 80],
                                  'src': 'media/formula.png'}]}

    def candidates(self, page):
        (self.inputs / '1.page.yaml').write_text(json.dumps(page, ensure_ascii=False))

    def run_check(self, **kw):
        return check(self.project, plan=self.plan, settings=self.settings, **kw)

    def fixed(self):
        self.project.mkdir()
        (self.project / 'media').mkdir()
        (self.project / 'media/formula.png').write_bytes(PNG)
        (self.project / 'media/formula.source.tex').write_text(r'k_r + \sigma_{opt}')
        page = copy.deepcopy(self.bad)
        page['elements'][0]['content']['text'] = '方法：阈值相关指标'
        page['elements'][1]['bounds'][3] = 150
        page['elements'][2]['content']['text'] = '本页公式给出了速率与净截面的关系。'
        page['elements'].append(text('reference', 'Ding, Zhang, CCS Chem., 2026', [36, 480, 888, 28]))
        return page

    def test_unpublished_candidates_report_real_defects_without_office_or_writes(self):
        self.candidates(self.bad)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('ansatz_slide.typography.check_pages', side_effect=AssertionError('Office called')), \
             patch('ansatz_slide.rendering.render_pptx', side_effect=AssertionError('render called')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('network called')):
            report = self.run_check()
        self.assertEqual('blocked', report['status'])
        codes = {i['code'] for i in report['issues']}
        self.assertTrue({'missing-asset', 'section-title', 'citation-review', 'plain-math', 'formula-review', 'sparse-panel'} <= codes)
        self.assertEqual([1], report['checkedPages'])
        self.assertEqual(str((self.inputs/'1.page.yaml').resolve()), report['pages'][0]['source'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse(self.project.exists())

    def test_flattened_math_diagnostic_recommends_formal_typesetting(self):
        page=self.fixed()
        page['elements'][2]['content']['text']='S1'
        self.candidates(page)
        report=self.run_check()
        warning=next(i for i in report['issues'] if i['code']=='plain-math')
        self.assertEqual(['S1'],warning['tokens'])
        self.assertEqual('warning',warning['severity'])
        self.assertIn('LaTeX',warning['message'])
        self.assertIn('native editable Office Math',warning['message'])
        self.assertIn('HTML sub/sup alone is not formal math',warning['message'])
        self.assertEqual(0,report['errors'])

    def test_native_math_is_recognized_without_requiring_a_formula_image(self):
        page=self.fixed()
        page['elements']=[e for e in page['elements'] if e['elementId']!='eq']
        page['elements'][2]['content']['text']=r'本页公式为 \(\sigma_{\mathrm{opt}} = \frac{a}{b}\)，使用 \(S_1\)。'
        self.candidates(page)
        report=self.run_check()
        self.assertEqual('passed',report['status'],report['issues'])
        self.assertEqual([],report['pages'][0]['formulas'])
        self.assertEqual([r'\sigma_{\mathrm{opt}} = \frac{a}{b}',r'S_1'],
                         [m['expression'] for m in report['pages'][0]['nativeMath']])

    def test_typeset_math_assets_with_sources_clear_the_advisories(self):
        self.candidates(self.fixed())
        report = self.run_check()
        self.assertEqual('passed', report['status'], report['issues'])
        self.assertEqual('eq', report['pages'][0]['formulas'][0]['element'])
        self.assertIn('scientific/mathematical meaning', report['notChecked'])
        self.assertFalse(list(self.root.rglob('*.pptx')))

    def test_unicode_math_including_html_indices_requires_typesetting(self):
        page = self.fixed()
        for value, symbol in [('σ', 'σ'), ('τ<sub>S1</sub>', 'τ'), ('R² = 0.8', '²'),
                              ('μJ/cm²', 'μ'), ('𝑥 ≤ 1', '≤'), ('&#963;<sub>opt</sub>', 'σ')]:
            with self.subTest(value=value):
                candidate = copy.deepcopy(page)
                candidate['elements'][2]['content']['text'] = value
                self.candidates(candidate)
                report = self.run_check()
                warning = next(i for i in report['issues'] if i['code'] == 'unicode-math')
                self.assertEqual('body', warning['element'])
                self.assertIn(symbol, warning['symbols'])
                self.assertEqual(0, report['errors'])
                self.assertFalse(any(i['code'] == 'unicode-math' for i in self.run_check(academic=False)['issues']))

    def test_unicode_math_in_table_cells_is_located_and_ordinary_prose_is_unaffected(self):
        page = self.fixed()
        page['elements'].append({'elementId': 'table', 'elementType': 'table', 'bounds': [350, 250, 280, 100],
                                 'columnWidths': [1], 'rowHeights': [1], 'rows': [[{'text': 'σ<sub>opt</sub>'}]]})
        self.candidates(page)
        report = self.run_check()
        warning = next(i for i in report['issues'] if i['code'] == 'unicode-math')
        self.assertEqual('table', warning['element'])
        self.assertEqual('elements[5].rows[0][0].text', warning['field'])
        page['elements'][-1]['rows'][0][0]['text'] = '研究者比较了候选与基准的净截面。'
        self.candidates(page)
        self.assertEqual('passed', self.run_check()['status'])

    def test_warnings_are_advisory_and_strict_is_an_explicit_exit_policy(self):
        page = self.fixed()
        page['elements'][0]['content']['text'] = 'A title without a section'
        self.candidates(page)
        args = ['deck', 'preflight', str(self.project), '--settings', str(self.settings), '--plan', str(self.plan)]
        with redirect_stdout(io.StringIO()) as output:
            code = main(args)
        report = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertEqual('needs_review', report['status'])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(1, main(args + ['--strict']))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(args + ['--basic', '--strict']))

    def test_remote_assets_are_not_fetched_and_offline_rejects_them(self):
        page = self.fixed()
        page['elements'][3]['src'] = 'https://example.invalid/formula.png'
        self.candidates(page)
        with patch('urllib.request.urlopen') as network:
            report = self.run_check(allow_remote=False)
        network.assert_not_called()
        self.assertTrue(any(i['code'] == 'remote-asset' and i['severity'] == 'error' for i in report['issues']))

    def nested_page(self, location, src):
        fill = {'type': 'image', 'src': src}
        page, theme = {'elements': []}, {}
        if location == 'background':
            page['background'] = fill
            field = 'background.src'
        elif location == 'shape':
            page['elements'] = [{'elementId': 'shape', 'elementType': 'shape',
                                 'shapeName': 'rect', 'bounds': [20, 80, 100, 60], 'fill': fill}]
            field = 'elements[0].fill.src'
        else:
            table = {'elementId': 'table', 'elementType': 'table', 'bounds': [20, 80, 100, 60],
                     'rowHeights': [1], 'columnWidths': [1], 'rows': [[{'text': 'A'}]]}
            page['elements'] = [table]
            if location == 'cell':
                table['rows'][0][0]['fill'] = fill
                field = 'elements[0].rows[0][0].fill.src'
            else:
                theme = {'tableStyles': {'default': {'firstRowStyle': {'fill': fill}}}}
                table['style'] = '$default'
                field = 'theme.tableStyles.default.firstRowStyle.fill.src'
        return page, theme, field

    def test_nested_and_theme_images_are_checked_with_exact_locations(self):
        self.project.mkdir()
        (self.project/'empty.png').write_bytes(b'')
        for location in ('background', 'shape', 'cell', 'theme'):
            for src in ('missing.png', 'empty.png', 'https://example.invalid/image.png', 'data:image/png;base64,'):
                with self.subTest(location=location, src=src):
                    page, theme, field = self.nested_page(location, src)
                    self.settings.write_text(json.dumps({'version': 'v2', 'size': [960, 540], 'theme': theme}))
                    self.candidates(page)
                    with patch('urllib.request.urlopen') as network:
                        report = self.run_check(academic=False, allow_remote=False)
                    network.assert_not_called()
                    self.assertEqual('blocked', report['status'], report)
                    self.assertEqual(1, report['errors'])
                    self.assertEqual(field, report['issues'][0]['field'])
                    self.assertEqual(None if location == 'theme' else 1, report['issues'][0]['page'])
                    assets = report['sharedAssets'] if location == 'theme' else report['pages'][0]['assets']
                    self.assertEqual(field, assets[0]['field'])
                    self.assertNotIn('data:image/png', json.dumps(report))

    def test_nested_asset_errors_block_export_before_office_and_resource_io(self):
        self.project.mkdir()
        (self.project/'empty.png').write_bytes(b'')
        output = self.root/'existing.pptx'
        output.write_bytes(b'previous delivery')
        for location in ('background', 'shape', 'cell', 'theme'):
            for src in ('empty.png', 'https://example.invalid/image.png'):
                with self.subTest(location=location, src=src):
                    page, theme, _ = self.nested_page(location, src)
                    (self.project/'1.page.yaml').write_text(json.dumps(page))
                    (self.project/'pptx.yaml').write_text(json.dumps({'version': 'v2', 'size': [960, 540],
                                                                   'pages': ['1.page.yaml'], 'theme': theme}))
                    with patch('ansatz_slide.typography.check_loaded') as measure, \
                         patch('ansatz_slide.project.resolve_images') as resolve:
                        with self.assertRaisesRegex(ValueError, 'Source preflight failed'):
                            export_project(self.project, output, force=True, measure_text=True, allow_remote=False)
                    measure.assert_not_called()
                    resolve.assert_not_called()
                    self.assertEqual(b'previous delivery', output.read_bytes())

    def test_skill_script_runs_without_office_on_path(self):
        self.candidates(self.fixed())
        script = Path(__file__).resolve().parents[2]/'skills/ansatz-slide/scripts/ansatz_slide.py'
        args = [sys.executable, str(script), 'deck', 'preflight', str(self.project),
                '--settings', str(self.settings), '--plan', str(self.plan), '--offline']
        result = subprocess.run(args, capture_output=True, text=True, timeout=10,
                                env={**os.environ, 'PATH': '', 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(0, result.returncode, result.stdout+result.stderr)
        self.assertEqual('passed', json.loads(result.stdout)['status'])

    def test_invalid_input_returns_a_source_error_without_publication(self):
        (self.inputs/'1.page.yaml').write_text('{invalid input')
        with redirect_stdout(io.StringIO()) as output:
            code = main(['deck', 'preflight', str(self.project), '--settings', str(self.settings), '--plan', str(self.plan)])
        self.assertEqual(1, code)
        self.assertEqual('input-invalid', json.loads(output.getvalue())['issues'][0]['code'])
        self.assertFalse(self.project.exists())

    def test_existing_project_selection_reports_real_page_numbers(self):
        page = self.fixed()
        for n in (1, 2):
            (self.project/f'{n}.page.yaml').write_text(json.dumps(page))
        (self.project/'pptx.yaml').write_text(json.dumps({'version': 'v2', 'size': [960, 540],
                                                       'pages': ['1.page.yaml', '2.page.yaml']}))
        report = check(self.project, numbers=[2])
        self.assertEqual([2], report['checkedPages'])
        self.assertEqual('2.page.yaml', report['pages'][0]['source'])
        with self.assertRaises(ValueError):
            check(self.project, numbers=[2, 2])

    def test_missing_asset_blocks_batch_before_preview_or_measurement(self):
        from ansatz_slide.batch_pages import import_pages
        self.candidates(self.bad)
        with patch('ansatz_slide.page_api.preview_batch') as preview:
            result = import_pages(self.project, self.plan, 'source-first',
                                  settings={'version': 'v2', 'size': [960, 540]})
        self.assertFalse(result['applied'])
        self.assertEqual('blocked', result['sourcePreflight']['status'])
        self.assertNotIn('textFit', result)
        preview.assert_not_called()
        self.assertFalse((self.project/'pptx.yaml').exists())

    def test_empty_asset_blocks_export_before_measurement_and_preserves_output(self):
        page = self.fixed()
        (self.project/'1.page.yaml').write_text(json.dumps(page))
        (self.project/'pptx.yaml').write_text(json.dumps({'version': 'v2', 'size': [960, 540], 'pages': ['1.page.yaml']}))
        (self.project/'media/formula.png').write_bytes(b'')
        output = self.root/'existing.pptx'
        output.write_bytes(b'keep existing delivery')
        with patch('ansatz_slide.typography.check_loaded') as measure, \
             patch('ansatz_slide.project.export_pptx') as writer:
            with self.assertRaisesRegex(ValueError, 'Source preflight failed'):
                export_project(self.project, output, force=True, measure_text=True)
        measure.assert_not_called()
        writer.assert_not_called()
        self.assertEqual(b'keep existing delivery', output.read_bytes())

    def test_revision_image_mapping_never_leaks_into_published_sources(self):
        from ansatz_slide.plan_revision import open_deck
        from ansatz_slide.revision import revise
        page = self.fixed()
        for n in (1, 2):
            (self.project/f'{n}.page.yaml').write_text(json.dumps(page))
        (self.project/'pptx.yaml').write_text(json.dumps({'version': 'v2', 'size': [960, 540], 'pages': ['1.page.yaml', '2.page.yaml']}))
        before = (self.project/'2.page.yaml').read_bytes()
        opened = open_deck(self.project, [1], render=False)
        plan = Path(opened['plan'])
        content = json.loads(plan.read_text())
        content['pages'][0]['edits'] = [{'element': 'title', 'changes': {'content': {'text': '结果：更新标题'}}}]
        plan.write_text(json.dumps(content))
        def render(source, folder, width):
            for n in (1, 2):
                (folder/f'page-{n:02}.png').write_bytes(PNG)
            return {'name': 'test stub'}
        with patch('ansatz_slide.plan_revision.check_pages', return_value=[{'status': 'passed', 'elements': []}]*2), \
             patch('ansatz_slide.plan_revision.render_pptx', side_effect=render):
            result = revise(self.project, plan, self.root/'revision.pptx')
        self.assertTrue(result['exported'], result['issues'])
        loaded, _ = load_project(self.project)
        for p in loaded['pages']:
            self.assertEqual('media/formula.png', next(e['src'] for e in p['elements'] if e['elementType'] == 'image'))
        self.assertEqual(before, (self.project/'2.page.yaml').read_bytes())
