"""Revision orchestration failure boundaries; real writer, stubbed render only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ansatz_slide import work_objects as work
from ansatz_slide.revision import revise
from ansatz_slide.package import inspect_pptx
from .test_page_api import fake_render, png


class RevisionTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'tmp/test-tmp';root.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.project=self.root/'project';self.project.mkdir()
        (self.project/'pptx.yaml').write_text(json.dumps({'version':'v2','size':[960,540],'pages':['1.page.yaml','2.page.yaml','3.page.yaml']}))
        for n in (1,2,3):
            (self.project/f'{n}.page.yaml').write_text(json.dumps({'elements':[{'elementId':'title','elementType':'text','bounds':[50,50,800,60],'content':{'text':f'Page {n}','fontSize':24}}]}))
        for name,value in [('ansatz_slide.page_api.checks.measure_text',{'status':'passed','elements':[]}),('ansatz_slide.typography.check_loaded',{'status':'passed'})]:
            mock=patch(name,return_value=value);mock.start();self.addCleanup(mock.stop)
        mock=patch('ansatz_slide.page_api.checks.render_pptx',side_effect=fake_render);mock.start();self.addCleanup(mock.stop)
        def final(source,folder,width):
            for n in range(1,inspect_pptx(source)['pageCount']+1):(folder/f'page-{n}.png').write_bytes(png())
            return {'name':'test stub'}
        mock=patch('ansatz_slide.revision.render_pptx',side_effect=final);self.renderer=mock.start();self.addCleanup(mock.stop)
        self.works=[work.open_page(self.project,n,render=False)['work'] for n in (1,2)]
        self.plan=self.root/'plan.json';self.output=self.root/'out.pptx'
        self.plan.write_text(json.dumps([{'work':ref,'edits':[{'element':'title','changes':{'content':{'text':f'New {n}'}}}]} for n,ref in enumerate(self.works,1)]))

    def test_success_single_delivery_and_unchanged_non_target(self):
        before=(self.project/'3.page.yaml').read_bytes()
        result=revise(self.project,self.plan,self.output)
        self.assertTrue(result['exported']);self.assertEqual([1,2],result['appliedPages'])
        self.assertEqual(3,inspect_pptx(self.output)['pageCount']);self.assertEqual(2,len(result['preview']['changedPageImages']))
        self.assertEqual(before,(self.project/'3.page.yaml').read_bytes())
        self.assertEqual(1,self.renderer.call_count)
        self.assertTrue(Path(result['report']).exists())

    def test_partial_failure_reports_applied_page_and_preserves_delivery(self):
        self.output.write_bytes(b'old delivery')
        plan=json.loads(self.plan.read_text());plan[1]['edits'][0]['changes']['bounds']=[900,50,800,60]
        self.plan.write_text(json.dumps(plan));before=(self.project/'2.page.yaml').read_bytes()
        result=revise(self.project,self.plan,self.output,force=True)
        self.assertEqual('blocked',result['status']);self.assertEqual([1],result['appliedPages'])
        self.assertFalse(result['exported']);self.assertEqual(b'old delivery',self.output.read_bytes())
        self.assertEqual(before,(self.project/'2.page.yaml').read_bytes());self.renderer.assert_not_called()
        self.assertEqual('blocked',result['pages'][1]['status'])

    def test_render_failure_never_replaces_old_delivery(self):
        self.output.write_bytes(b'old delivery');self.renderer.side_effect=RuntimeError('renderer unavailable')
        result=revise(self.project,self.plan,self.output,force=True)
        self.assertFalse(result['exported']);self.assertEqual([1,2],result['appliedPages'])
        self.assertEqual(b'old delivery',self.output.read_bytes());self.assertIn('renderer unavailable',str(result['issues']))

    def test_stale_second_work_rejected_before_any_write(self):
        target=self.project/'2.page.yaml';target.write_text(target.read_text().replace('Page 2','External'))
        before=(self.project/'1.page.yaml').read_bytes()
        with self.assertRaisesRegex(ValueError,'changed'):revise(self.project,self.plan,self.output)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes());self.assertFalse(self.output.exists())

    def test_bad_later_patch_rejected_before_any_write(self):
        plan=json.loads(self.plan.read_text());plan[1]['edits'][0]['element']='missing';self.plan.write_text(json.dumps(plan))
        before=(self.project/'1.page.yaml').read_bytes()
        with self.assertRaises(ValueError):revise(self.project,self.plan,self.output)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())

    def test_source_changed_during_final_render_not_published(self):
        self.output.write_bytes(b'old delivery');original=self.renderer.side_effect
        def changed(*args):
            result=original(*args)
            p=self.project/'3.page.yaml';p.write_text(p.read_text().replace('Page 3','External'))
            return result
        self.renderer.side_effect=changed
        result=revise(self.project,self.plan,self.output,force=True)
        self.assertFalse(result['exported']);self.assertEqual(b'old delivery',self.output.read_bytes())
        self.assertIn('Source changed',str(result['issues']))

    def test_duplicate_page_plan_and_source_output_cannot_mutate(self):
        before=(self.project/'1.page.yaml').read_bytes()
        original=self.plan.read_text();plan=json.loads(original)
        self.plan.write_text(json.dumps([plan[0],plan[0]]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):revise(self.project,self.plan,self.output)
        self.plan.write_text(original)
        with self.assertRaisesRegex(ValueError,'overwrite'):revise(self.project,self.plan,self.project/'1.page.yaml',force=True)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())

    def test_foreign_work_cannot_be_batched_into_project(self):
        import shutil
        other=self.root/'other';shutil.copytree(self.project,other,ignore=shutil.ignore_patterns('.ansatz'))
        foreign=work.open_page(other,2,render=False)['work']
        plan=json.loads(self.plan.read_text());plan[1]['work']=foreign;self.plan.write_text(json.dumps(plan))
        before=(self.project/'1.page.yaml').read_bytes()
        with self.assertRaisesRegex(ValueError,'another project'):revise(self.project,self.plan,self.output)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())

    def test_local_edit_and_layout_share_one_revision(self):
        plan=json.loads(self.plan.read_text())
        plan[0]['layout']=[{'kind':'row','items':['title'],'bounds':[60,120,800,80]}]
        self.plan.write_text(json.dumps(plan))
        result=revise(self.project,self.plan,self.output)
        self.assertTrue(result['exported'],result['issues'])
        from ansatz_slide.page_api import snapshot
        title=snapshot(self.project)['pages'][0]['elements'][0]
        self.assertEqual([60,130,800,60],title['bounds'])
        self.assertEqual('New 1',title['content']['text'])
        self.assertEqual(24,title['content']['fontSize'])

    def test_invalid_later_layout_is_preflighted_before_any_write(self):
        plan=json.loads(self.plan.read_text())
        plan[1]['layout']=[{'kind':'row','items':['title'],'bounds':[0,0,100,80]}]
        self.plan.write_text(json.dumps(plan));before=(self.project/'1.page.yaml').read_bytes()
        with self.assertRaisesRegex(ValueError,'fit'):revise(self.project,self.plan,self.output)
        self.assertEqual(before,(self.project/'1.page.yaml').read_bytes())
        self.assertFalse(self.output.exists())

    def new_asset_plan(self):
        asset=self.project/'new.png';asset.write_bytes(png())
        page=json.loads((self.project/'2.page.yaml').read_text())
        page['elements'].append({'elementId':'new-image','elementType':'image',
                                 'src':'new.png','bounds':[100,200,100,100]})
        candidate=self.root/'new.page.yaml';candidate.write_text(json.dumps(page))
        plan=json.loads(self.plan.read_text());plan[1]={'work':self.works[1],'content':str(candidate)}
        self.plan.write_text(json.dumps(plan))
        return asset

    def test_new_candidate_asset_is_protected_before_any_page_write(self):
        asset=self.new_asset_plan()
        before={p:p.read_bytes() for p in self.project.glob('*.yaml')};data=asset.read_bytes()
        with self.assertRaisesRegex(ValueError,'overwrite'):
            revise(self.project,self.plan,asset,force=True)
        self.assertEqual(data,asset.read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_new_candidate_asset_change_during_final_render_blocks_delivery(self):
        asset=self.new_asset_plan();self.output.write_bytes(b'old delivery')
        original=self.renderer.side_effect
        def changed(*args):
            result=original(*args);asset.write_bytes(b'changed');return result
        self.renderer.side_effect=changed
        result=revise(self.project,self.plan,self.output,force=True)
        self.assertFalse(result['exported']);self.assertEqual(b'old delivery',self.output.read_bytes())
        self.assertIn('Source changed',str(result['issues']))

    def test_new_candidate_asset_exports_when_unchanged(self):
        asset=self.new_asset_plan();before=asset.read_bytes()
        result=revise(self.project,self.plan,self.output)
        self.assertTrue(result['exported'],result['issues']);self.assertEqual(before,asset.read_bytes())
