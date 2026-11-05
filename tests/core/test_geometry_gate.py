"""Mandatory geometry gate: real policy, failure preservation and repair paths."""
import copy
import io
from ansatz_slide.project import SOURCE_HEADER
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ansatz_slide import export_pptx
from ansatz_slide.cli import main
from ansatz_slide import page_api
from ansatz_slide.occupancy import GeometryError, analyze, require_pass
from ansatz_slide.project import create_project, export_project, load_project
from ansatz_slide.validation import validate_project
from .test_page_api import fake_render


def page(overlap=False):
    return {'elements':[
        {'elementId':'a','elementType':'text','bounds':[1,1,5,5],'content':{'text':'A'}},
        {'elementId':'b','elementType':'text','bounds':[3 if overlap else 8,1,5,5],'content':{'text':'B'}}]}


class GeometryGateTests(unittest.TestCase):
    def setUp(self):
        text_mock=patch('ansatz_slide.page_api.checks.measure_text',return_value={'status':'passed','elements':[],'engine':'stub for geometry tests'})
        text_mock.start();self.addCleanup(text_mock.stop)
        root=Path(__file__).resolve().parents[2]/'tmp/test-tmp';root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=root);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest={'version':'v2','size':[20,20],'pages':['1.page.yaml','2.page.yaml']}
        self.write('pptx.yaml',self.manifest)
        self.write('1.page.yaml',page());self.write('2.page.yaml',page())

    def write(self,name,data):
        p=self.root/name;p.write_text(json.dumps(data));return p

    def sources(self):
        return {p.name:p.read_bytes() for p in self.root.glob('*.yaml')}

    def test_core_and_cli_gate_before_resources_or_output_even_with_force(self):
        self.write('1.page.yaml',page(True))
        data,_=load_project(self.root)
        with patch('ansatz_slide.Package',side_effect=AssertionError('must not package')):
            with self.assertRaisesRegex(GeometryError,'a/b'):export_pptx(data)
        out=self.root/'existing.pptx';out.write_bytes(b'original')
        with patch('ansatz_slide.project.resolve_images',side_effect=AssertionError('must not read images')):
            with self.assertRaises(GeometryError):export_project(self.root,out,force=True)
        self.assertEqual(b'original',out.read_bytes())
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            self.assertEqual(1,main(['export',str(self.root),'-o',str(out),'--force']))
            self.assertEqual(1,main(['validate',str(self.root)]))
        self.assertEqual(b'original',out.read_bytes())

    def test_explicit_pair_reason_passes_but_does_not_exempt_third_element_or_clipping(self):
        p=page(True);p['allowedOverlaps']=[{'elements':['a','b'],'reason':'Label over background'}]
        report,_=analyze([20,20],p);require_pass(report)
        self.assertEqual(1,len(report['approvedOverlaps']))
        self.assertTrue(export_pptx({'size':[20,20],'pages':[p]}).startswith(b'PK'))
        p['elements'].append({**copy.deepcopy(p['elements'][1]),'elementId':'c'})
        with self.assertRaisesRegex(GeometryError,'a/c'):require_pass(analyze([20,20],p)[0])
        p['elements'].pop();p['elements'][0]['bounds'][0]=-1
        with self.assertRaisesRegex(GeometryError,'out of bounds'):require_pass(analyze([20,20],p)[0])

    def test_declarations_reject_blank_unknown_duplicate_and_wildcard(self):
        for declarations in [True,[{'elements':['a','b'],'reason':' '}],
            [{'elements':['a','missing'],'reason':'x'}],[{'elements':['a','a'],'reason':'x'}],
            [{'elements':['*','b'],'reason':'x'}],
            [{'elements':['a','b'],'reason':'x'},{'elements':['b','a'],'reason':'x'}]]:
            p=page(True);p['allowedOverlaps']=declarations
            with self.subTest(declarations=declarations),self.assertRaises(GeometryError):
                validate_project(self.manifest,[p,page()],check_files=False)

    def test_fractional_contact_passes_despite_shared_cell(self):
        p=page();p['elements'][0]['bounds']=[0,0,.5,1];p['elements'][1]['bounds']=[.5,0,.5,1]
        report,_=analyze([20,20],p);self.assertEqual(1,report['overlapCells']);require_pass(report)

    def test_raw_python_export_cannot_hide_invalid_bounds(self):
        for bounds in [[0,0,-1,3],[0,0,float('nan'),3],[0,0,0,3]]:
            p=page();p['elements'][0]['bounds']=bounds
            with self.assertRaises(GeometryError):export_pptx({'size':[20,20],'pages':[p]})

    def test_incremental_export_does_not_replace_output_on_geometry_failure(self):
        from ansatz_slide.incremental import replace_from_project
        baseline=self.root/'baseline.pptx';export_project(self.root,baseline)
        self.write('1.page.yaml',page(True))
        output=self.root/'result.pptx';output.write_bytes(b'previous delivery')
        before=baseline.read_bytes()
        with self.assertRaises(GeometryError):
            replace_from_project(baseline,self.root,1,output,force=True)
        self.assertEqual(b'previous delivery',output.read_bytes())
        self.assertEqual(before,baseline.read_bytes())

    def test_manifest_creation_checks_all_pages_and_export_rechecks_edits(self):
        (self.root/'pptx.yaml').unlink()  # Creation requires a directory without a formal manifest.
        draft=self.write('deck.draft.yaml',self.manifest);out=self.root/'new.pptx.yaml'
        self.write('2.page.yaml',page(True));before=self.sources()
        with self.assertRaises(GeometryError):create_project(draft,out)
        self.assertFalse(out.exists());self.assertEqual(before,self.sources())
        self.write('2.page.yaml',page());result=create_project(draft,out)
        self.assertEqual('passed',result['geometryStatus']);self.assertEqual(SOURCE_HEADER.encode()+draft.read_bytes(),out.read_bytes())
        with self.assertRaises(FileExistsError):create_project(draft,out)
        self.write('2.page.yaml',page(True))
        with self.assertRaises(GeometryError):export_project(out,self.root/'bad.pptx')
        self.assertFalse((self.root/'bad.pptx').exists())

    def test_draft_change_during_precheck_does_not_publish_manifest(self):
        from ansatz_slide.occupancy import require_pages
        (self.root/'pptx.yaml').unlink()  # Creation requires a directory without a formal manifest.
        draft=self.write('deck.draft.yaml',self.manifest);out=self.root/'new.pptx.yaml'
        def changed(size,pages):
            reports=require_pages(size,pages);self.write('2.page.yaml',page(True));return reports
        with patch('ansatz_slide.occupancy.require_pages',side_effect=changed):
            with self.assertRaisesRegex(RuntimeError,'changed during'):create_project(draft,out)
        self.assertFalse(out.exists())

    def test_blocked_page_check_returns_repair_session_without_pptx_or_office(self):
        self.write('1.page.yaml',page(True));session=self.root/'session'
        with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=AssertionError('must not render')):
            r=page_api.check_page(self.root/'pptx.yaml',1,session)
        self.assertEqual('blocked',r['geometry']['status']);self.assertIsNone(r['image']);self.assertIsNone(r['previewPptx'])
        self.assertFalse(list(session.rglob('*.pptx')))
        self.assertTrue(Path(r['geometry']['files']['report']).is_file())
        with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=fake_render):
            fixed=page_api.edit_page(session,r['token'],element_id='b',changes={'bounds':[8,1,5,5]})
        self.assertEqual('passed',fixed['geometry']['status']);self.assertTrue(Path(fixed['previewPptx']).is_file())

    def test_failed_edit_insert_split_merge_and_manifest_move_preserve_sources(self):
        with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=fake_render):
            r=page_api.check_page(self.root/'pptx.yaml',1,self.root/'s1')
            other=page_api.check_page(self.root/'pptx.yaml',2,self.root/'s2')
        bad=self.write('bad.page.yaml',page(True));before=self.sources()
        actions=[
            lambda:page_api.edit_page(self.root/'s1',r['token'],bad),
            lambda:page_api.change_order(self.root/'s1',r['token'],'insert',content=bad),
            lambda:page_api.reshape_pages(self.root/'s1',r['token'],[bad,bad]),
            lambda:page_api.reshape_pages(self.root/'s1',r['token'],[bad],self.root/'s2',other['token'])]
        with patch('ansatz_slide.page_api.checks.render_pptx',side_effect=AssertionError('must not render')):
            for action in actions:
                with self.assertRaises(GeometryError):action()
                self.assertEqual(before,self.sources())
        # An unchecked change to another page cannot be published via order edits.
        self.write('2.page.yaml',page(True));before=self.sources()
        with self.assertRaises(GeometryError):
            page_api.change_order(self.root/'s1',r['token'],'insert',content=self.root/'1.page.yaml',allow_duplicates=True)
        self.assertEqual(before,self.sources())

    def test_diagnostic_cli_exit_is_failure_with_json_artifacts(self):
        self.write('1.page.yaml',page(True));output=io.StringIO()
        with redirect_stdout(output),redirect_stderr(io.StringIO()):
            status=main(['page','check-overlap','--project',str(self.root/'pptx.yaml'),'--page','1',
                         '--output',str(self.root/'diag')])
        self.assertEqual(1,status);self.assertEqual('blocked',json.loads(output.getvalue())['status'])
