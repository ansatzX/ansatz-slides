"""Batched project plans retain version/file protection and review identity."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ansatz_slide.plan_revision import open_deck
from ansatz_slide.revision import revise
from ansatz_slide.review import annotate
from . import test_revision as legacy_tests


class PlanRevisionTests(unittest.TestCase):
    def setUp(self):
        legacy_tests.RevisionTests.setUp(self)
        self.opened=open_deck(self.project,[1,2],render=False)
        self.plan=Path(self.opened['plan'])
        document=json.loads(self.plan.read_text())
        for entry in document['pages']:
            entry['edits']=[{'element':'title','changes':{'content':{'text':f"Changed {entry['page']}"}}}]
        self.plan.write_text(json.dumps(document))
        def measure(size,pages,theme,folder):
            return [{'status':'passed','elements':[]} for _ in pages]
        mock=patch('ansatz_slide.plan_revision.check_pages',side_effect=measure);self.measure=mock.start();self.addCleanup(mock.stop)
        mock=patch('ansatz_slide.plan_revision.render_pptx',side_effect=self.renderer.side_effect);self.final_render=mock.start();self.addCleanup(mock.stop)

    def test_one_batch_one_render_and_same_plan_replay(self):
        before=(self.project/'3.page.yaml').read_bytes()
        with patch('ansatz_slide.work_objects.update',side_effect=AssertionError('per-page workflow used')):
            result=revise(self.project,self.plan,self.output)
        self.assertTrue(result['exported'],result['issues'])
        self.assertEqual([1,2],result['appliedPages'])
        self.assertEqual(1,self.measure.call_count);self.assertEqual(1,self.final_render.call_count)
        self.assertEqual(before,(self.project/'3.page.yaml').read_bytes())
        replay=revise(self.project,self.plan,self.output)
        self.assertTrue(replay['replayed']);self.assertEqual(1,self.final_render.call_count)
        review=json.loads(Path(result['review']['manifest']).read_text())
        self.assertEqual('delivery',review['kind'])
        self.assertEqual(['not_reviewed']*3,[p['visual']['status'] for p in review['pages']])
        self.assertTrue(Path(result['review']['viewer']).is_file())
        self.assertTrue(all((Path(result['review']['manifest']).parent/p['image']).is_file() for p in review['pages']))

    def test_failed_read_preview_still_returns_one_usable_plan(self):
        with patch('ansatz_slide.page_api.preview_batch',side_effect=RuntimeError('preview unavailable')):
            result=open_deck(self.project,[1,2],render=True)
        self.assertEqual('blocked',result['status'])
        self.assertTrue(Path(result['plan']).exists())
        self.assertTrue(Path(result['base']).exists())
        self.assertIn('preview unavailable',result['issues'][0]['message'])

    def test_write_failure_rolls_back_earlier_source_and_retries_same_plan(self):
        from ansatz_slide.file_transactions import preserving_replace
        before={p:p.read_bytes() for p in self.project.glob('*.yaml')}
        self.output.write_bytes(b'old')
        count=0
        def fail_second(*args):
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('write failed')
            return preserving_replace(*args)
        with patch('ansatz_slide.plan_revision.preserving_replace',side_effect=fail_second):
            failed=revise(self.project,self.plan,self.output,force=True)
        self.assertFalse(failed['exported']);self.assertEqual(b'old',self.output.read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        fixed=revise(self.project,self.plan,self.output,force=True)
        self.assertTrue(fixed['exported'],fixed['issues'])

    def test_stale_snapshot_rejected_without_source_writes(self):
        (self.project/'3.page.yaml').write_text((self.project/'3.page.yaml').read_text().replace('Page 3','external'))
        before=(self.project/'1.page.yaml').read_bytes()
        with self.assertRaisesRegex(ValueError,'changed'):revise(self.project,self.plan,self.output)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes());self.assertFalse(self.output.exists())

    def test_geometry_failure_same_plan_can_repair_and_preserves_content(self):
        document=json.loads(self.plan.read_text());document['pages'][0]['edits'][0]['changes']['bounds']=[950,50,800,60]
        self.plan.write_text(json.dumps(document));before=(self.project/'1.page.yaml').read_bytes()
        failed=revise(self.project,self.plan,self.output)
        self.assertFalse(failed['exported']);self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())
        self.final_render.assert_not_called();self.assertTrue(Path(failed['review']['viewer']).exists())
        document['pages'][0]['edits'][0]['changes']['bounds']=[50,50,800,60]
        document['pages'][0]['edits'][0]['changes']['content']['text']='deleted meaning'
        self.plan.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError,'preserved'):revise(self.project,self.plan,self.output)
        document['pages'][0]['edits'][0]['changes']['content']['text']='Changed 1'
        self.plan.write_text(json.dumps(document))
        fixed=revise(self.project,self.plan,self.output);self.assertTrue(fixed['exported'],fixed['issues'])

    def test_text_failure_returns_candidate_review_without_writing_sources(self):
        before=(self.project/'1.page.yaml').read_bytes()
        self.measure.return_value=None
        self.measure.side_effect=lambda *args:[{'status':'blocked','elements':[{'elementId':'title','status':'overflow','reason':'too tall'}]},
                                               {'status':'passed','elements':[]},{'status':'passed','elements':[]}]
        result=revise(self.project,self.plan,self.output)
        self.assertFalse(result['exported']);self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())
        self.assertFalse(self.output.exists());self.assertEqual('candidate',result['review']['kind'])
        data=json.loads(Path(result['review']['manifest']).read_text())
        self.assertIsNotNone(data['pages'][0]['image']);self.assertEqual('title',data['pages'][0]['issues'][0]['element'])

    def test_final_render_failure_preserves_all_sources_and_old_output(self):
        before={p:p.read_bytes() for p in self.project.glob('*.yaml')}
        self.output.write_bytes(b'old');self.final_render.side_effect=RuntimeError('render failed')
        result=revise(self.project,self.plan,self.output,force=True)
        self.assertFalse(result['exported']);self.assertEqual(b'old',self.output.read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_review_note_never_changes_program_checks_and_rejects_old_version(self):
        result=revise(self.project,self.plan,self.output);folder=Path(result['review']['manifest']).parent
        before=json.loads((folder/'review.json').read_text())
        annotate(folder,1,'needs_fix','Figure labels are too small')
        after=json.loads((folder/'review.json').read_text())
        self.assertEqual(before['pages'][0]['checks'],after['pages'][0]['checks'])
        self.assertEqual('needs_fix',after['pages'][0]['visual']['status'])
        self.output.write_bytes(b'new version')
        with self.assertRaisesRegex(ValueError,'changed'):annotate(folder,1,'reviewed','looks okay')

    def test_output_cannot_replace_plan_or_new_asset(self):
        before=self.plan.read_bytes()
        with self.assertRaisesRegex(ValueError,'overwrite'):revise(self.project,self.plan,self.plan,force=True)
        self.assertEqual(before,self.plan.read_bytes())

    def test_concurrent_change_during_render_prevents_all_publication(self):
        original=self.final_render.side_effect;before=(self.project/'1.page.yaml').read_bytes()
        def changed(*args):
            value=original(*args)
            p=self.project/'3.page.yaml';p.write_text(p.read_text().replace('Page 3','external'))
            return value
        self.final_render.side_effect=changed
        result=revise(self.project,self.plan,self.output)
        self.assertFalse(result['exported']);self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())
        self.assertFalse(self.output.exists())
