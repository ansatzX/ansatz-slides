"""Regression cases from the independent whole-project review; renderer is stubbed."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ansatz_slide import page_api as api, work_objects as work
from ansatz_slide.outline import outline
from ansatz_slide.project import create_project, find_manifest, parse_document
from .test_page_api import fake_render, png
from .test_work_objects import page

REPO = Path(__file__).resolve().parents[2]


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        text_mock=patch('ansatz_slide.page_api.measure_text',return_value={'status':'passed','elements':[],'engine':'stub for transaction/geometry tests'})
        text_mock.start();self.addCleanup(text_mock.stop)
        scratch=REPO/'tmp/test-tmp';scratch.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=scratch);self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.deck=self.root/'deck';self.deck.mkdir()
        self.settings={'version':'v2','size':[20,20]}
        self.render=patch('ansatz_slide.page_api.render_pptx',side_effect=fake_render)
        self.render.start();self.addCleanup(self.render.stop)

    def write(self,path,value):
        path.write_text(json.dumps(value));return path

    def project(self, pages=None):
        pages=pages or [page()]
        names=[f'{i}.page.yaml' for i in range(len(pages))]
        for name,value in zip(names,pages):self.write(self.deck/name,value)
        self.write(self.deck/'pptx.yaml',{**self.settings,'pages':names})

    def asset(self):
        path=self.deck/'figure.png';path.write_bytes(png());return path

    def image(self):
        return {'elementId':'figure','elementType':'image','bounds':[11,8,8,8],'src':'figure.png'}

    def test_new_edit_asset_changed_before_and_after_publication(self):
        self.project();asset=self.asset();source=self.deck/'0.page.yaml';before=source.read_bytes()
        for during in ('draft','publication'):
            with self.subTest(during=during):
                asset.write_bytes(png())
                session=self.root/during;opened=api.check_page(self.deck,1,session)
                candidate=opened['pageSource'];candidate['elements'].append(self.image())
                content=self.write(self.root/'candidate.yaml',candidate)
                real_write=api.session_write;real_publish=api.preserving_replace
                def write(folder,name,data):
                    real_write(folder,name,data)
                    if name=='page.page.yaml':asset.write_bytes(png(b'\xff\x00\x00'))
                def publish(*args):
                    result=real_publish(*args);asset.write_bytes(png(b'\xff\x00\x00'));return result
                target='session_write' if during=='draft' else 'preserving_replace'
                with patch('ansatz_slide.page_api.'+target,side_effect=write if during=='draft' else publish):
                    with self.assertRaisesRegex(RuntimeError,'[Cc]oncurrent|changed'):
                        api.edit_page(session,opened['token'],content)
                self.assertEqual(before,source.read_bytes())

    def test_create_detects_earlier_page_asset_change(self):
        asset=self.asset();original=page(overlap=True);original['elements'].append(self.image())
        blocked=work.create(self.deck,self.settings,original);self.assertEqual('blocked',blocked['status'])
        first={'elements':[original['elements'][0],self.image()]}
        second={'elements':[original['elements'][1]]}
        paths=[self.write(self.root/f'part{i}.yaml',p) for i,p in enumerate([first,second])]
        real=api.preview;calls=[]
        def preview(*args,**kwargs):
            result=real(*args,**kwargs);calls.append(result)
            if len(calls)==1:asset.write_bytes(png(b'\xff\x00\x00'))
            return result
        with patch('ansatz_slide.page_api.preview',side_effect=preview):
            result=work.change(blocked['work'],'split',paths)
        self.assertFalse(result['applied']);self.assertEqual(2,len(calls))
        self.assertFalse((self.deck/'pptx.yaml').exists())

    def test_create_retracts_manifest_if_asset_changes_during_publish(self):
        asset=self.asset();value=page();value['elements'].append(self.image())
        real=work.atomic_write
        def write(path,data,*args,**kwargs):
            result=real(path,data,*args,**kwargs)
            if Path(path).name=='pptx.yaml':asset.write_bytes(png(b'\xff\x00\x00'))
            return result
        with patch('ansatz_slide.work_objects.atomic_write',side_effect=write):
            result=work.create(self.deck,self.settings,value)
        self.assertFalse(result['applied']);self.assertFalse((self.deck/'pptx.yaml').exists())
        self.assertTrue(list((self.deck/'.ansatz-recovery').glob('*/failed-creation')))

    def external_manifest(self):
        self.write(self.deck/'external.page.yaml',page())
        return self.write(self.deck/'external.pptx.yaml',{**self.settings,'pages':['external.page.yaml']})

    def test_named_manifest_blocks_create_retry(self):
        blocked=work.create(self.deck,self.settings,page(overlap=True));external=self.external_manifest()
        result=work.update(blocked['work'],element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('conflict',result['status']);self.assertEqual(external,find_manifest(self.deck))

    def test_named_manifest_racing_publication_is_preserved(self):
        real=work.atomic_write
        def write(path,data,*args,**kwargs):
            result=real(path,data,*args,**kwargs)
            if Path(path).name=='pptx.yaml':self.external_manifest()
            return result
        with patch('ansatz_slide.work_objects.atomic_write',side_effect=write):
            result=work.create(self.deck,self.settings,page())
        self.assertFalse(result['applied']);self.assertEqual('external.pptx.yaml',find_manifest(self.deck).name)

    def test_legacy_create_honors_named_manifest(self):
        external=self.external_manifest()
        draft=self.write(self.deck/'draft.yaml',{**self.settings,'pages':['external.page.yaml']})
        with self.assertRaisesRegex(ValueError,'already has a manifest'):
            create_project(draft,self.deck/'pptx.yaml')
        self.assertEqual(external,find_manifest(self.deck))

    def test_process_death_releases_all_lock_kinds_and_live_owner_excludes(self):
        env={**os.environ,'PYTHONPATH':str(REPO/'src')}
        script='import os,sys\nfrom pathlib import Path\nfrom ansatz_slide.page_api import lock\nwith lock(Path(sys.argv[1])):\n os._exit(0)\n'
        for name in ('.ansatz-page-edit.lock','.work.lock','.outline.lock','.session.lock'):
            path=self.root/name
            with self.subTest(lock=name):
                child=subprocess.run([sys.executable,'-c',script,str(path)],env=env,capture_output=True)
                self.assertEqual(0,child.returncode,child.stderr)
                with api.lock(path):
                    rejected=subprocess.run([sys.executable,'-c',script,str(path)],env=env,capture_output=True)
                    self.assertNotEqual(0,rejected.returncode)
                    self.assertIn(b'Another edit/check',rejected.stderr)
                with api.lock(path):pass
        self.project();opened=work.open_page(self.deck,1)
        subprocess.run([sys.executable,'-c',script,str(self.deck/'.ansatz-page-edit.lock')],env=env,check=True)
        self.assertTrue(work.update(opened['work'],element='body',changes={'content':{'text':'Recovered'}})['applied'])

    def test_outline_tracks_assets_neighbors_and_theme_but_not_order_token(self):
        asset=self.asset();value=page();value['elements'].append(self.image());self.project([value,page()])
        for i in (1,2):outline(self.deck,i,{'purpose':'Explain'})
        snap=api.snapshot(self.deck);token=api.presentation_token(snap,1)
        self.assertFalse(outline(self.deck)['pages'][0]['needsReview'])
        asset.write_bytes(png(b'\xff\x00\x00'))
        result=outline(self.deck)['pages'];self.assertTrue(result[0]['needsReview']);self.assertTrue(result[1]['relationNeedsReview'])
        self.assertTrue(work.open_page(self.deck,1)['context']['current']['needsReview'])
        for i in (1,2):outline(self.deck,i,{'purpose':'Explain'})
        manifest=self.deck/'pptx.yaml';value=parse_document(manifest.read_text(),'manifest');value['theme']={'colors':{'accent':'#FF0000'}};self.write(manifest,value)
        self.assertTrue(all(p['needsReview'] for p in outline(self.deck)['pages']))
        snap=api.snapshot(self.deck);token=api.presentation_token(snap,1)
        value['pages'].reverse();self.write(manifest,value)
        self.assertEqual(token,api.presentation_token(api.snapshot(self.deck),2))

    def test_distribution_contract_covers_new_modules_tests_and_skill(self):
        spec=importlib.util.spec_from_file_location('distribution_verifier',REPO/'scripts/verify_distribution.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        required,tests=verifier.required_files(REPO)
        self.assertIn('tests/core/test_review_fixes.py',tests)
        for name in ('work_objects','page_api','occupancy','outline','gates','rendering','file_transactions'):
            path=f'ansatz_slide/{name}.py';self.assertIn(path,required)
            with self.assertRaisesRegex(ValueError,name):verifier.require_present(required-{path},required)
        self.assertIn('ansatz_slide/skill/reference/review-cli.md',required)

    def test_distribution_verifier_rejects_incomplete_archives(self):
        from zipfile import ZipFile
        import tarfile
        import io
        spec=importlib.util.spec_from_file_location('distribution_verifier',REPO/'scripts/verify_distribution.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        required,tests=verifier.required_files(REPO)
        wheel=self.root/'test.whl';sdist=self.root/'test.tar.gz'
        extras={'ansatz_slide/shape_names.txt','ansatz_slide/templates/ppt/theme/theme1.xml'}
        source={('skills/ansatz-slide/'+p.removeprefix('ansatz_slide/skill/')) if p.startswith('ansatz_slide/skill/') else 'src/'+p for p in required}|tests
        def archives(omit_wheel=None,omit_source=None):
            with ZipFile(wheel,'w') as archive:
                for name in (required|extras)-{omit_wheel}:archive.writestr(name,b'x')
            with tarfile.open(sdist,'w:gz') as archive:
                for name in source-{omit_source}:
                    info=tarfile.TarInfo('test/'+name);info.size=1;archive.addfile(info,io.BytesIO(b'x'))
        args=[sys.executable,str(REPO/'scripts/verify_distribution.py'),'--wheel',str(wheel),'--sdist',str(sdist)]
        archives();result=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)
        for omitted in ('ansatz_slide/work_objects.py','ansatz_slide/skill/reference/review-cli.md'):
            archives(omit_wheel=omitted);result=subprocess.run(args,capture_output=True,text=True)
            self.assertNotEqual(0,result.returncode);self.assertIn(omitted,result.stderr)
        archives(omit_source='tests/core/test_review_fixes.py');result=subprocess.run(args,capture_output=True,text=True)
        self.assertNotEqual(0,result.returncode);self.assertIn('test_review_fixes.py',result.stderr)
