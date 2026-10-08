import copy
import json
import yaml
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ansatz_slide import batch_pages as batch, work_objects as work, page_api as api
from .test_page_api import fake_render

BASE=Path(__file__).resolve().parents[2]/'tmp/test-tmp'

def page(text):
    return {'elements':[{'elementId':'body','elementType':'text','bounds':[10,10,300,50],'content':{'text':text}}]}

class FeedbackWorkflow(unittest.TestCase):
    def setUp(self):
        BASE.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=BASE);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'deck';self.project.mkdir()
        self.settings={'version':'v2','size':[960,540]}
        for name,side in [('measure_text',{'status':'passed','elements':[]}),('render_pptx',fake_render)]:
            mock=patch('ansatz_slide.page_api.'+name,**({'return_value':side} if isinstance(side,dict) else {'side_effect':side}))
            mock.start();self.addCleanup(mock.stop)
    def plan(self,texts):
        names=[]
        for i,t in enumerate(texts):
            path=self.root/f'input-{i}.page.yaml';path.write_text(json.dumps(page(t)));names.append(path.name)
        path=self.root/'plan.json';path.write_text(json.dumps(names));return path
    def test_batch_create_replay_insert_and_id_conflict(self):
        plan=self.plan(['first','second'])
        result=batch.import_pages(self.project,plan,'create',settings=self.settings)
        self.assertTrue(result['applied'],result)
        snap=api.snapshot(self.project);before=copy.deepcopy(snap['tracked'])
        replay=batch.import_pages(self.project,plan,'create',settings=self.settings)
        self.assertTrue(replay['replayed']);self.assertTrue(api.unchanged(before))
        inserted=batch.import_pages(self.project,self.plan(['middle','another']),'insert',after=1)
        self.assertTrue(inserted['applied'],inserted)
        self.assertEqual([p['elements'][0]['content']['text'] for p in api.snapshot(self.project)['pages']],['first','middle','another','second'])
        with self.assertRaisesRegex(ValueError,'different input'):batch.import_pages(self.project,self.plan(['changed']),'create',settings=self.settings)
    def test_duplicate_rejection_and_failed_candidate_resume(self):
        blocked=batch.import_pages(self.project,self.plan(['same','same']),'dup',settings=self.settings)
        self.assertFalse(blocked['applied']);self.assertFalse((self.project/'pptx.yaml').exists())
        Path(blocked['candidateFiles'][1]).write_text(json.dumps(page('different')))
        repaired=batch.resume(blocked['resumeToken'])
        self.assertTrue(repaired['applied'],repaired)
        again=batch.import_pages(self.project,self.plan(['same']),'dup-existing')
        self.assertFalse(again['applied'])
    def test_publication_receipt_loss_recovers_without_duplicate(self):
        result=batch.import_pages(self.project,self.plan(['one','two']),'receipt',settings=self.settings)
        self.assertTrue(result['applied'],result)
        (Path(result['resumeToken'])/'result.json').unlink()
        recovered=batch.resume(result['resumeToken'])
        self.assertTrue(recovered['recovered']);self.assertEqual(len(api.snapshot(self.project)['pages']),2)
    def test_failed_render_and_source_change_do_not_publish(self):
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('fail render')):
            blocked=batch.import_pages(self.project,self.plan(['one','two']),'failure',settings=self.settings)
        self.assertFalse(blocked['applied']);self.assertFalse((self.project/'pptx.yaml').exists())
        self.assertTrue(batch.resume(blocked['resumeToken'])['applied'])
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('fail render')):
            blocked=batch.import_pages(self.project,self.plan(['three']),'source')
        manifest=self.project/'pptx.yaml';manifest.write_text(manifest.read_text()+'\n')
        before=api.snapshot(self.project)['tracked']
        result=batch.resume(blocked['resumeToken']);self.assertFalse(result['applied']);self.assertTrue(api.unchanged(before))
    def test_stable_work_resume_and_deleted_pending_insert(self):
        batch.import_pages(self.project,self.plan(['one','two']),'init',settings=self.settings)
        opened=work.open_page(self.project,2,render=False)
        content=self.root/'insert.json';content.write_text(json.dumps(page('pending')))
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('fail render')):
            pending=work.change(opened['work'],'insert',[content])
        self.assertFalse(pending['applied'])
        self.assertEqual(work.resume(opened['resumeToken'])['work'],pending['work'])
        manifest=self.project/'pptx.yaml';data=yaml.safe_load(manifest.read_text());data['pages'].pop();manifest.write_text(json.dumps(data))
        conflict=work.update(pending['work']);self.assertEqual(conflict['status'],'conflict')
        self.assertNotIn('list index',str(conflict['issues']))
        with self.assertRaisesRegex(ValueError,'anchor removed'):work.rebase(pending['resumeToken'])
        rebased=work.rebase(pending['resumeToken'],1)
        self.assertFalse(rebased['applied']);self.assertEqual(rebased['candidates'][0]['page'],page('pending'))
        applied=work.update(rebased['work']);self.assertTrue(applied['applied'],applied)
        self.assertEqual([p['elements'][0]['content']['text'] for p in api.snapshot(self.project)['pages']],['one','pending'])
    def test_reorder_rebase_follows_path_and_preserves_pending(self):
        batch.import_pages(self.project,self.plan(['one','two']),'init',settings=self.settings)
        opened=work.open_page(self.project,2,render=False)
        content=self.root/'edit.json';content.write_text(json.dumps(page('retained')))
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('fail render')):
            pending=work.update(opened['work'],content)
        manifest=self.project/'pptx.yaml';data=yaml.safe_load(manifest.read_text());data['pages'].reverse();manifest.write_text(json.dumps(data))
        result=work.rebase(pending['resumeToken']);self.assertEqual(result['page'],1)
        self.assertEqual(result['candidates'][0]['page'],page('retained'));self.assertFalse(result['applied'])

    def test_external_source_edit_during_publication_is_preserved(self):
        batch.import_pages(self.project,self.plan(['one']),'init',settings=self.settings)
        before=api.snapshot(self.project);manifest=before['manifestPath'].read_bytes()
        original=batch.preserving_replace
        def concurrent(*args):
            publication=original(*args)
            before['paths'][0].write_text(json.dumps(page('external')))
            return publication
        with patch('ansatz_slide.batch_pages.preserving_replace',side_effect=concurrent):
            result=batch.import_pages(self.project,self.plan(['two']),'race')
        self.assertFalse(result['applied']);self.assertEqual(before['manifestPath'].read_bytes(),manifest)
        self.assertEqual(api.snapshot(self.project)['pages'][0],page('external'))

    def test_table_measurement_with_real_consumer(self):
        import shutil
        from ansatz_slide.table_measurement import check_tables
        if not shutil.which('soffice') or not shutil.which('pdftoppm'):
            self.skipTest('LibreOffice/Poppler not installed')
        table={'elementId':'dense','elementType':'table','bounds':[10,10,400,50],
               'columnWidths':[.5,.5],'rowHeights':[1/19]*19,
               'rows':[[{'text':str(i)},{'text':''}] for i in range(19)],
               'style':{'cellStyle':{'fontSize':9.5}}}
        original=copy.deepcopy(table)
        small=check_tables([table],{},self.root/'small')[0]
        self.assertEqual(small['status'],'overflow');self.assertGreater(small['requiredHeight'],50)
        self.assertEqual(table,original)
        table['bounds'][3]=600
        large=check_tables([table],{},self.root/'large')[0]
        self.assertEqual(large['status'],'passed',large)

    def test_single_insert_duplicates_are_blocked_before_render_and_can_opt_in(self):
        batch.import_pages(self.project,self.plan(['one','two']),'init',settings=self.settings)
        opened=work.open_page(self.project,1,render=False)
        candidate=self.root/'again.json'
        # A different mapping serialization still denotes the same page.
        candidate.write_text(json.dumps(page('two'),sort_keys=True))
        before=api.snapshot(self.project)['tracked']
        with patch('ansatz_slide.page_api.preview',side_effect=AssertionError('duplicate must not render')):
            blocked=work.change(opened['work'],'insert',[candidate])
        self.assertFalse(blocked['applied']);self.assertIn('Duplicate page',str(blocked['issues']))
        self.assertTrue(api.unchanged(before))
        allowed=work.update(blocked['work'],allow_duplicates=True)
        self.assertTrue(allowed['applied'],allowed['issues'])
        self.assertEqual(len(api.snapshot(self.project)['pages']),3)
        stale=work.change(opened['work'],'insert',[candidate],allow_duplicates=True)
        self.assertEqual(stale['status'],'conflict')

    def test_single_insert_after_delete_restores_content_without_opt_in(self):
        batch.import_pages(self.project,self.plan(['one','two']),'init',settings=self.settings)
        opened=work.open_page(self.project,2,render=False)
        removed=work.change(opened['work'],'remove')
        candidate=self.root/'restore.json';candidate.write_text(json.dumps(page('two')))
        restored=work.change(removed['work'],'insert',[candidate])
        self.assertTrue(restored['applied'],restored['issues'])
        self.assertEqual(len(api.snapshot(self.project)['pages']),2)
