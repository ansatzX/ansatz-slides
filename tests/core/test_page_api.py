"""Single-page API scope/attention tests; preview stub is not a visual quality test."""
from ansatz_slide.project import parse_document
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from ansatz_slide import page_api
from ansatz_slide.inspection import inspect_pptx


def png(color=b'\x00\x00\x00'):
    def chunk(kind, body):
        return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+
            chunk(b'IDAT',zlib.compress(b'\0'+color))+chunk(b'IEND',b''))


def fake_render(source, folder, width):
    if inspect_pptx(source)['pageCount'] != 1:
        raise AssertionError('Page API leaked the full deck into its preview')
    (folder/'page-1.png').write_bytes(png())
    return {'name':'single-page test stub; not visual evidence'}


class PageAPITests(unittest.TestCase):
    def setUp(self):
        text_mock=patch('ansatz_slide.page_api.measure_text',return_value={'status':'passed','elements':[],'engine':'stub for transaction/geometry tests'})
        text_mock.start();self.addCleanup(text_mock.stop)
        scratch=Path(__file__).resolve().parents[2]/'tmp/test-tmp';scratch.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.project=self.root/'project';self.project.mkdir()
        self.session=self.root/'session'
        self.manifest=self.project/'pptx.yaml'
        self.manifest.write_text(json.dumps({'version':'v2','size':[960,540],'pages':[f'{i}.page.yaml' for i in range(1,4)]}))
        for i in range(1,4):self.write_page(i)
        self.render_patch=patch('ansatz_slide.page_api.render_pptx',side_effect=fake_render)
        self.render_patch.start();self.addCleanup(self.render_patch.stop)

    def write_page(self,number,suffix=''):
        value={'pageType':'content','elements':[
            {'elementId':'title','elementType':'text','bounds':[50,30,800,60],
             'content':{'text':f'Page {number} premise{suffix}','fontSize':30}},
            {'elementId':'body','elementType':'text','bounds':[50,130,800,60],
             'content':{'text':f'PRIVATE_BODY_{number}{suffix}','fontSize':18}}]}
        (self.project/f'{number}.page.yaml').write_text(json.dumps(value));return value

    def originals(self):
        return {p.name:p.read_bytes() for p in self.project.iterdir() if p.is_file() and p.name != ".ansatz-page-edit.lock"}

    def draft(self, response, text='Edited local body'):
        value=response['pageSource'];value['elements'][1]['content']['text']=text
        Path(response['editablePage']).write_text(json.dumps(value))

    def test_check_exposes_only_selected_page_and_neighbor_titles(self):
        r=page_api.check_page(self.project,2,self.session)
        self.assertEqual(2,r['page']);self.assertEqual([1,3],[p['page'] for p in r['adjacentContext']])
        serialized=json.dumps(r)
        self.assertIn('PRIVATE_BODY_2',serialized)
        self.assertNotIn('PRIVATE_BODY_1',serialized);self.assertNotIn('PRIVATE_BODY_3',serialized)
        self.assertEqual(1,inspect_pptx(r['previewPptx'])['pageCount'])
        for filename in r['geometry']['files'].values():
            self.assertTrue(Path(filename).is_file())
        geometry_report=Path(r['geometry']['files']['occupancyImage']).with_name('report.json')
        self.assertEqual(r['geometry'],parse_document(geometry_report.read_text(), "test source"))
        self.assertNotIn('PRIVATE_BODY',json.dumps(page_api.check_deck(self.project)))

    def test_edit_writes_only_pinned_page_and_returns_new_local_preview(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals();self.draft(r)
        after=page_api.edit_page(self.session,r['token'])
        changed=[p for p,b in before.items() if (self.project/p).read_bytes()!=b]
        self.assertEqual(['2.page.yaml'],changed);self.assertEqual([2],after['changedPages'])
        self.assertNotEqual(r['token'],after['token']);self.assertEqual('Edited local body',after['pageSource']['elements'][1]['content']['text'])
        self.assertTrue(Path(after['image']).is_file());self.assertEqual(1,inspect_pptx(after['previewPptx'])['pageCount'])
        with self.assertRaisesRegex(ValueError,'Stale page'):
            page_api.edit_page(self.session,r['token'])

    def test_deck_or_batch_payload_cannot_write_any_source(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        for value in [{'pages':[r['pageSource'],r['pageSource']]},[r['pageSource'],r['pageSource']]]:
            Path(r['editablePage']).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'exactly one page'):
                page_api.edit_page(self.session,r['token'])
            self.assertEqual(before,self.originals())

    def test_preview_failure_preserves_original_and_keeps_draft(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals();self.draft(r)
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('no renderer')):
            with self.assertRaisesRegex(RuntimeError,'no renderer'):
                page_api.edit_page(self.session,r['token'])
        self.assertEqual(before,self.originals());self.assertIn('Edited local body',Path(r['editablePage']).read_text())
        with page_api.lock(self.project/'.ansatz-page-edit.lock'): pass  # Kernel ownership released; inode remains.

    def test_unrelated_page_change_is_preserved_but_target_change_is_stale(self):
        r=page_api.check_page(self.project,2,self.session);self.draft(r)
        self.write_page(1,' changed elsewhere');other=(self.project/'1.page.yaml').read_bytes()
        result=page_api.edit_page(self.session,r['token'])
        self.assertEqual(other,(self.project/'1.page.yaml').read_bytes())
        self.write_page(2,' externally revised')
        with self.assertRaisesRegex(ValueError,'Stale page'):
            page_api.edit_page(self.session,result['token'])

    def test_shared_asset_change_stales_target(self):
        image=self.project/'figure.png';image.write_bytes(png())
        p=self.project/'2.page.yaml';value=parse_document(p.read_text(), "test source");value['elements'].append(
            {'elementId':'fig','elementType':'image','bounds':[50,250,200,200],'src':'figure.png'})
        p.write_text(json.dumps(value));r=page_api.check_page(self.project,2,self.session)
        image.write_bytes(png(b'\xff\x00\x00'))
        with self.assertRaisesRegex(ValueError,'Stale page'):
            page_api.edit_page(self.session,r['token'])

    def test_session_cannot_retarget_overwrite_sources_or_discard_draft(self):
        r=page_api.check_page(self.project,2,self.session)
        with self.assertRaisesRegex(ValueError,'pinned'):
            page_api.check_page(self.project,3,self.session)
        self.draft(r)
        with self.assertRaisesRegex(ValueError,'unapplied draft'):
            page_api.check_page(self.project,2,self.session)
        self.assertIn('Edited local body',Path(r['editablePage']).read_text())
        with self.assertRaisesRegex(ValueError,'must not contain original'):
            page_api.check_page(self.project,2,self.project)

    def test_duplicate_page_alias_cannot_modify_multiple_slide_positions(self):
        value=parse_document(self.manifest.read_text(), "test source");value['pages'][2]='2.page.yaml';self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'reuses a page file'):
            page_api.check_page(self.project,2,self.session)

    def test_concurrent_source_change_during_preview_does_not_apply_candidate(self):
        r=page_api.check_page(self.project,2,self.session);self.draft(r);before=(self.project/'2.page.yaml').read_bytes()
        def changing(source,folder,width):
            result=fake_render(source,folder,width);self.write_page(1,' concurrent');return result
        with patch('ansatz_slide.page_api.render_pptx',side_effect=changing):
            with self.assertRaisesRegex(RuntimeError,'changed during preview'):
                page_api.edit_page(self.session,r['token'])
        self.assertEqual(before,(self.project/'2.page.yaml').read_bytes())

    def test_split_and_merge_preserve_sources_and_splice_only_local_order(self):
        before=self.originals();r=page_api.check_page(self.project,2,self.session)
        a=self.root/'a.page.yaml';b=self.root/'b.page.yaml'
        a.write_text(json.dumps(r['pageSource']));b.write_text(json.dumps(r['pageSource']))
        result=page_api.reshape_pages(self.session,r['token'],[a,b])
        self.assertEqual(4,result['pageCount'])
        order=parse_document(self.manifest.read_text(), "test source")['pages']
        self.assertEqual('1.page.yaml',order[0]);self.assertEqual('3.page.yaml',order[-1])
        for name,data in before.items():
            if name!='pptx.yaml':self.assertEqual(data,(self.project/name).read_bytes())
        with self.assertRaisesRegex(ValueError,'Stale'):
            page_api.edit_page(self.session,r['token'])
        left=page_api.check_page(self.project,2,self.root/'left')
        right=page_api.check_page(self.project,3,self.root/'right')
        merged=page_api.reshape_pages(self.root/'left',left['token'],[a],self.root/'right',right['token'])
        self.assertEqual(3,merged['pageCount'])
        final=parse_document(self.manifest.read_text(), "test source")['pages']
        self.assertEqual(order[0],final[0]);self.assertEqual(order[-1],final[-1])
        self.assertTrue(all((self.project/name).is_file() for name in order))

    def test_merge_requires_adjacent_checked_sources_and_current_tokens(self):
        a=page_api.check_page(self.project,1,self.session)
        c=page_api.check_page(self.project,3,self.root/'third')
        before=self.originals()
        with self.assertRaisesRegex(ValueError,'immediately following'):
            page_api.reshape_pages(self.session,a['token'],[a['editablePage']],self.root/'third',c['token'])
        b=page_api.check_page(self.project,2,self.root/'second')
        self.write_page(2,' changed');before=self.originals()
        with self.assertRaisesRegex(ValueError,'Stale adjacent'):
            page_api.reshape_pages(self.session,a['token'],[a['editablePage']],self.root/'second',b['token'])
        self.assertEqual(before,self.originals())

    def test_split_failure_and_invalid_payload_do_not_change_order(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        with self.assertRaisesRegex(ValueError,'at least two'):
            page_api.reshape_pages(self.session,r['token'],[r['editablePage']])
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('render failed')):
            with self.assertRaisesRegex(RuntimeError,'render failed'):
                page_api.reshape_pages(self.session,r['token'],[r['editablePage']]*2)
        self.assertEqual(before,self.originals())
        with patch('ansatz_slide.page_api.preserving_replace',side_effect=OSError('manifest write failed')):
            with self.assertRaisesRegex(OSError,'manifest write failed'):
                page_api.reshape_pages(self.session,r['token'],[r['editablePage']]*2)
        for name,data in before.items():self.assertEqual(data,(self.project/name).read_bytes())

    def test_split_rejects_candidate_asset_change_between_previews(self):
        r=page_api.check_page(self.project,2,self.session)
        asset=self.project/'new.png';asset.write_bytes(png())
        candidate=r['pageSource'];candidate['elements'].append({'elementId':'new','elementType':'image','bounds':[20,300,100,100],'src':'new.png'})
        draft=self.root/'with-image.page.yaml';draft.write_text(json.dumps(candidate))
        manifest_before=self.manifest.read_bytes();calls=0
        def changing(source,folder,width):
            nonlocal calls
            calls+=1;result=fake_render(source,folder,width)
            if calls==2:asset.write_bytes(png(b'\xff\x00\x00'))
            return result
        with patch('ansatz_slide.page_api.render_pptx',side_effect=changing):
            with self.assertRaisesRegex(RuntimeError,'asset edit'):
                page_api.reshape_pages(self.session,r['token'],[draft,r['editablePage']])
        self.assertEqual(manifest_before,self.manifest.read_bytes())

    def test_patch_changes_one_element_and_preserves_omitted_fields(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        result=page_api.edit_page(self.session,r['token'],element_id='body',
            changes={'content':{'text':'A focused change'},'bounds':[60,150,800,100]})
        value=result['pageSource'];original=json.loads(before['2.page.yaml'])
        self.assertEqual(original['elements'][0],value['elements'][0])
        self.assertEqual(18,value['elements'][1]['content']['fontSize'])
        self.assertEqual('A focused change',value['elements'][1]['content']['text'])
        self.assertEqual([60,150,800,100],value['elements'][1]['bounds'])
        for name,data in before.items():
            if name!='2.page.yaml':self.assertEqual(data,(self.project/name).read_bytes())
        self.assertNotEqual(r['token'],result['token']);self.assertTrue(Path(result['image']).is_file())

    def test_patch_rejects_unknown_identity_invalid_fields_and_pending_draft(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        for element,changes in [('missing',{'bounds':[1,1,10,10]}),('body',{}),
                ('body',{'elementId':'title'}),('body',{'elementType':'image'}),
                ('body',{'pages':[]}),('body',{'bounds':[0,0,-1,1]})]:
            with self.assertRaises(ValueError):
                page_api.edit_page(self.session,r['token'],element_id=element,changes=changes)
            self.assertEqual(before,self.originals())
        self.draft(r)
        with self.assertRaisesRegex(ValueError,'unapplied draft'):
            page_api.edit_page(self.session,r['token'],element_id='body',changes={'content':{'text':'no'}})

    def test_patch_image_reference_preserves_original_media(self):
        old=self.project/'old.png';new=self.project/'new.png'
        old.write_bytes(png());new.write_bytes(png(b'\xff\x00\x00'))
        value=parse_document((self.project/'2.page.yaml').read_text(), "test source")
        value['elements'].append({'elementId':'figure','elementType':'image','bounds':[40,250,150,150],'src':'old.png'})
        (self.project/'2.page.yaml').write_text(json.dumps(value))
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        result=page_api.edit_page(self.session,r['token'],element_id='figure',changes={'src':'new.png'})
        self.assertEqual('new.png',result['pageSource']['elements'][-1]['src'])
        for name in ['old.png','new.png']:self.assertEqual(before[name],(self.project/name).read_bytes())

    def test_insert_before_first_and_after_last_preserves_all_existing_sources(self):
        r=page_api.check_page(self.project,1,self.session);before=self.originals()
        result=page_api.change_order(self.session,r['token'],'insert',content=r['editablePage'],position='before',allow_duplicates=True)
        order=parse_document(self.manifest.read_text(), "test source")['pages']
        self.assertEqual(1,result['page']);self.assertEqual(4,result['pageCount'])
        self.assertEqual(['1.page.yaml','2.page.yaml','3.page.yaml'],order[1:])
        self.assertTrue(Path(result['image']).is_file())
        for name,data in before.items():
            if name!='pptx.yaml':self.assertEqual(data,(self.project/name).read_bytes())
        end=page_api.check_page(self.project,4,self.root/'end')
        appended=page_api.change_order(self.root/'end',end['token'],'insert',content=end['editablePage'],allow_duplicates=True)
        self.assertEqual(5,appended['page'])
        self.assertEqual(order,parse_document(self.manifest.read_text(), "test source")['pages'][:-1])

    def test_move_forward_backward_uses_anchor_identity(self):
        a=page_api.check_page(self.project,1,self.session)
        c=page_api.check_page(self.project,3,self.root/'anchor');before=self.originals()
        moved=page_api.change_order(self.session,a['token'],'move',anchor_session=self.root/'anchor',anchor_token=c['token'])
        self.assertEqual(3,moved['page']);self.assertEqual(['2.page.yaml','3.page.yaml','1.page.yaml'],parse_document(self.manifest.read_text(), "test source")['pages'])
        source=page_api.check_page(self.project,3,self.root/'source2');anchor=page_api.check_page(self.project,1,self.root/'anchor2')
        page_api.change_order(self.root/'source2',source['token'],'move',position='before',anchor_session=self.root/'anchor2',anchor_token=anchor['token'])
        self.assertEqual(['1.page.yaml','2.page.yaml','3.page.yaml'],parse_document(self.manifest.read_text(), "test source")['pages'])
        for name,data in before.items():
            if name!='pptx.yaml':self.assertEqual(data,(self.project/name).read_bytes())

    def test_move_rejects_self_and_stale_anchor_without_writes(self):
        a=page_api.check_page(self.project,1,self.session)
        with self.assertRaisesRegex(ValueError,'itself'):
            page_api.change_order(self.session,a['token'],'move',anchor_session=self.session,anchor_token=a['token'])
        c=page_api.check_page(self.project,3,self.root/'anchor');self.write_page(3,'changed');before=self.originals()
        with self.assertRaisesRegex(ValueError,'Stale'):
            page_api.change_order(self.session,a['token'],'move',anchor_session=self.root/'anchor',anchor_token=c['token'])
        self.assertEqual(before,self.originals())

    def test_remove_retains_file_and_rejects_last_page(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        result=page_api.change_order(self.session,r['token'],'remove')
        self.assertEqual(2,result['pageCount']);self.assertEqual(['1.page.yaml','3.page.yaml'],parse_document(self.manifest.read_text(), "test source")['pages'])
        for name,data in before.items():
            if name!='pptx.yaml':self.assertEqual(data,(self.project/name).read_bytes())
        for i in range(2):
            r=page_api.check_page(self.project,1,self.root/f'remove-{i}')
            if i==0:page_api.change_order(self.root/f'remove-{i}',r['token'],'remove')
            else:
                with self.assertRaisesRegex(ValueError,'last page'):
                    page_api.change_order(self.root/f'remove-{i}',r['token'],'remove')

    def test_insert_failure_preserves_order_and_sources(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('render failed')):
            with self.assertRaisesRegex(RuntimeError,'render failed'):
                page_api.change_order(self.session,r['token'],'insert',content=r['editablePage'],allow_duplicates=True)
        self.assertEqual(before,self.originals())
        with patch('ansatz_slide.page_api.preserving_replace',side_effect=OSError('manifest failed')):
            with self.assertRaisesRegex(OSError,'manifest failed'):
                page_api.change_order(self.session,r['token'],'insert',content=r['editablePage'],allow_duplicates=True)
        for name,data in before.items():self.assertEqual(data,(self.project/name).read_bytes())

    def test_session_output_links_rejected_without_project_writes(self):
        before=self.originals()
        for i,name in enumerate(['page.page.yaml','session.json','versions','.session.lock']):
            session=self.root/f'link-{i}';session.mkdir()
            (session/name).symlink_to(self.project if name=='versions' else self.project/'1.page.yaml')
            with self.assertRaisesRegex(ValueError,'symlink'):
                page_api.check_page(self.project,2,session)
            self.assertEqual(before,self.originals())

    def test_late_session_file_link_does_not_redirect_write(self):
        r=page_api.check_page(self.project,2,self.session);before=self.originals()
        Path(r['editablePage']).unlink();Path(r['editablePage']).symlink_to(self.project/'1.page.yaml')
        with self.assertRaisesRegex(ValueError,'symlink'):
            page_api.edit_page(self.session,r['token'])
        self.assertEqual(before,self.originals())

    def test_prepublication_chmod_failure_and_state_failure_restore_source(self):
        r=page_api.check_page(self.project,2,self.session);self.draft(r);before=self.originals()
        original_chmod=Path.chmod
        def fail(path,*args,**kwargs):
            if path.name=='candidate':raise OSError('mode failure')
            return original_chmod(path,*args,**kwargs)
        with patch.object(Path,'chmod',fail):
            with self.assertRaisesRegex(OSError,'mode failure'):
                page_api.edit_page(self.session,r['token'])
        self.assertEqual(before,self.originals())
        original=page_api.session_write
        def state_fail(session,name,data):
            if name=='session.json':raise OSError('state failure')
            return original(session,name,data)
        with patch('ansatz_slide.page_api.session_write',side_effect=state_fail):
            with self.assertRaisesRegex(OSError,'state failure'):
                page_api.edit_page(self.session,r['token'])
        self.assertEqual(before,self.originals())
        self.assertEqual(r['token'],parse_document((self.session/'session.json').read_text(), "test source")['token'])

    def test_external_change_during_draft_write_is_not_overwritten(self):
        r=page_api.check_page(self.project,2,self.session);self.draft(r)
        original=page_api.session_write
        def race(session,name,data):
            if name=='page.page.yaml':self.write_page(2,' external')
            return original(session,name,data)
        with patch('ansatz_slide.page_api.session_write',side_effect=race):
            with self.assertRaisesRegex(RuntimeError,'Concurrent'):
                page_api.edit_page(self.session,r['token'])
        self.assertIn('external',(self.project/'2.page.yaml').read_text())

    def test_concurrent_target_version_at_rename_is_retained(self):
        from ansatz_slide import file_transactions as ft
        r=page_api.check_page(self.project,2,self.session);self.draft(r)
        original=ft.os.rename;target=self.project/'2.page.yaml'
        def race(src,dst,*args,**kwargs):
            if Path(src)==target and Path(dst).name=='previous':self.write_page(2,' at commit')
            return original(src,dst,*args,**kwargs)
        with patch.object(ft.os,'rename',race):
            with self.assertRaisesRegex(RuntimeError,'conflict'):
                page_api.edit_page(self.session,r['token'])
        self.assertIn('at commit',target.read_text())
        backups=list((self.project/'.ansatz-recovery').glob('*/previous'))
        self.assertTrue(any('at commit' in p.read_text() for p in backups))

    def test_writer_creating_destination_during_publish_is_preserved(self):
        from ansatz_slide import file_transactions as ft
        r=page_api.check_page(self.project,2,self.session);self.draft(r)
        original=ft.os.link;target=self.project/'2.page.yaml';injected=False
        def race(src,dst,*args,**kwargs):
            nonlocal injected
            if Path(src).name=='candidate' and Path(dst)==target and not injected:
                injected=True;self.write_page(2,' new writer')
            return original(src,dst,*args,**kwargs)
        with patch.object(ft.os,'link',race):
            with self.assertRaisesRegex(RuntimeError,'conflict'):
                page_api.edit_page(self.session,r['token'])
        self.assertIn('new writer',target.read_text())

    def test_remove_response_source_matches_surviving_page(self):
        for number in [1,2,3]:
            with self.subTest(number=number):
                # Restore only the manifest for independent removals; sources persist.
                self.manifest.write_text(json.dumps({'version':'v2','size':[960,540],'pages':[f'{i}.page.yaml' for i in [1,2,3]]}))
                session=self.root/f'remove-identity-{number}'
                r=page_api.check_page(self.project,number,session)
                result=page_api.change_order(session,r['token'],'remove')
                order=parse_document(self.manifest.read_text(), "test source")['pages']
                self.assertEqual(str(self.project/order[result['page']-1]),result['sourcePage'])
                self.assertEqual(str(self.project/f'{number}.page.yaml'),result['removedSource'])
