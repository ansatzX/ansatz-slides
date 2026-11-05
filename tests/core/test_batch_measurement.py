"""Batch performance must preserve measurement results and publication gates."""
import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from ansatz_slide import typography, batch_pages, page_api
from . import test_feedback_workflow as feedback

class BatchMeasurement(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'tmp/test-tmp';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    @unittest.skipUnless(all(shutil.which(x) for x in ('soffice','pdftotext','pdffonts')), 'Office/Poppler required')
    def test_real_batch_matches_separate_measurement_including_failure_and_alignment(self):
        def page(text,height,align):
            return {'elements':[{'elementId':'same-id','elementType':'text','bounds':[20,20,220,height],
                'content':{'text':text,'fontFamily':'Arial','fontSize':20,'align':align}}]}
        pages=[page('Readable text',70,['left','middle']),page('This sentence wraps onto several lines in a narrow frame.',12,'left'),
               page(r'Native math \(x_i\)',60,'left')]
        original=copy.deepcopy(pages)
        separate=[typography.check_page([960,540],p,{},self.root/f'single-{i}') for i,p in enumerate(pages)]
        with patch('ansatz_slide.typography.run_command',wraps=typography.run_command) as commands:
            combined=typography.check_pages([960,540],pages,{},self.root/'batch')
        office_calls=[c for c in commands.call_args_list if '--convert-to' in c.args[0]]
        self.assertEqual(len(office_calls),1)
        self.assertEqual(pages,original)
        self.assertEqual([p['page'] for p in combined],[1,2,3])
        self.assertEqual([p['status'] for p in combined],['passed','blocked','blocked'])
        for old,new in zip(separate,combined):
            self.assertEqual(old['elements'],new['elements'])
        with self.assertRaises(typography.TextFitError):typography.require_pass(combined[1])

    def test_chunking_preserves_duplicate_ids_and_page_ownership(self):
        pages=[{'elements':[{'elementId':f'e-{j}','elementType':'text','bounds':[0,0,30,30],
                            'content':{'text':'x'}} for j in range(70)]} for _ in range(3)]
        def measured(size,page,theme,folder):
            return {'status':'passed','elements':[{'elementId':e['elementId'],'status':'passed'} for e in page['elements']],
                    'unmeasuredObjects':[]}
        with patch('ansatz_slide.typography.check_page',side_effect=measured) as check:
            result=typography.check_pages([960,540],pages,{},self.root)
        self.assertEqual(check.call_count,3)
        for report in result:self.assertEqual([x['elementId'] for x in report['elements']],[f'e-{j}' for j in range(70)])

class BatchPublication(unittest.TestCase):
    setUp = feedback.FeedbackWorkflow.setUp
    plan = feedback.FeedbackWorkflow.plan
    # Reuse transaction fixture while adding real batch boundary assertions.
    def test_geometry_failure_identifies_candidate_and_publishes_nothing(self):
        plan=self.plan(['valid','bad'])
        import json
        candidate=self.root/'input-1.page.yaml';value=json.loads(candidate.read_text())
        value['elements'][0]['bounds']=[950,0,300,50];candidate.write_text(json.dumps(value))
        with patch('ansatz_slide.page_api.checks.render_pptx') as render:
            result=batch_pages.import_pages(self.project,plan,'geometry',settings=self.settings)
        self.assertFalse(result['applied']);self.assertEqual(result['checkingCandidate'],2)
        self.assertFalse((self.project/'pptx.yaml').exists());render.assert_not_called()

    def test_eight_pages_share_one_render_and_one_measurement_batch(self):
        with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=feedback.batch_render) as render, \
             patch('ansatz_slide.page_api.checks.measure_pages',return_value=[{'page':i,'status':'passed','elements':[]} for i in range(1,9)]) as measure:
            result=batch_pages.import_pages(self.project,self.plan([f'page {i}' for i in range(8)]),'batch-count',settings=self.settings)
        self.assertTrue(result['applied'],result)
        self.assertEqual(8,len(result['pages']))
        self.assertEqual(1,render.call_count)
        self.assertEqual(1,measure.call_count)

    def test_missing_batch_image_rejects_all_pages_and_can_resume(self):
        with patch('ansatz_slide.page_api.checks.render_pptx',return_value={'name':'broken renderer'}):
            result=batch_pages.import_pages(self.project,self.plan(['one','two']),'images',settings=self.settings)
        self.assertFalse(result['applied']);self.assertFalse((self.project/'pptx.yaml').exists())
        self.assertTrue(batch_pages.resume(result['resumeToken'])['applied'])
