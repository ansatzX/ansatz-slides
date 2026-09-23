"""Work-object attention boundaries, retained failure evidence, and version safety."""
from ansatz_slide.project import parse_document, SOURCE_HEADER
import copy
import io
import json
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ansatz_slide import work_objects as work
from ansatz_slide.outline import outline
from ansatz_slide.cli import main
from .test_page_api import fake_render


def page(overlap=False,text='Body'):
    return {'elements':[
        {'elementId':'title','elementType':'text','bounds':[1,1,8,3],'content':{'text':'Title'}},
        {'elementId':'body','elementType':'text','bounds':[1,2 if overlap else 8,8,3],'content':{'text':text}}]}


def decode(matrix,kind):
    rows=[]
    for band in matrix[kind]:
        row=[value for value,length in band['runs'] for _ in range(length)]
        rows.extend([row]*band['rowCount'])
    return rows


class WorkObjectTests(unittest.TestCase):
    def setUp(self):
        text_mock=patch('ansatz_slide.page_api.measure_text',return_value={'status':'passed','elements':[],'engine':'stub for transaction/geometry tests'})
        text_mock.start();self.addCleanup(text_mock.stop)
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.project=self.root/'deck';self.project.mkdir()
        self.settings={'version':'v2','size':[20,20]}
        self.write('pptx.yaml',{**self.settings,'pages':['1.page.yaml','2.page.yaml']})
        self.write('1.page.yaml',page());self.write('2.page.yaml',page(text='PRIVATE_OTHER_BODY'))
        fake=patch('ansatz_slide.page_api.render_pptx',side_effect=fake_render);fake.start();self.addCleanup(fake.stop)

    def write(self,name,value):
        path=self.project/name;path.write_text(json.dumps(value));return path

    def sources(self):return {p.name:p.read_bytes() for p in self.project.glob('*.yaml')}

    def test_open_returns_one_page_matrix_and_context_without_token(self):
        r=work.open_page(self.project,1)
        self.assertEqual('ready',r['status']);self.assertNotIn('token',r)
        self.assertNotIn('PRIVATE_OTHER_BODY',json.dumps(r))
        m=r['candidates'][0]['geometry']['matrices'];counts=decode(m,'counts');binary=decode(m,'occupancy')
        self.assertEqual([20,20],m['shape']);self.assertEqual(20,len(counts));self.assertEqual(20,len(counts[0]))
        self.assertEqual([[int(x>0) for x in row] for row in counts],binary)

    def test_blocked_candidate_is_retained_and_repaired_without_resubmitting_page(self):
        r=work.open_page(self.project,1);before=self.sources()
        bad=work.update(r['work'],element='body',changes={'bounds':[1,2,8,3],'content':{'text':'Retain this new text'}})
        self.assertEqual('blocked',bad['status']);self.assertFalse(bad['applied']);self.assertEqual(before,self.sources())
        m=bad['candidates'][0]['geometry']['matrices'];self.assertEqual(2,decode(m,'counts')[2][1])
        self.assertTrue(m['conflictRegions']);self.assertTrue(Path(bad['candidates'][0]['editable']).exists())
        fixed=work.update(bad['work'],element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('applied',fixed['status']);self.assertTrue(fixed['applied'])
        self.assertEqual('Retain this new text',fixed['candidates'][0]['page']['elements'][1]['content']['text'])
        self.assertTrue(Path(fixed['candidates'][0]['preview']['image']).exists())
        self.assertEqual(before['2.page.yaml'],self.sources()['2.page.yaml'])

    def test_old_reference_and_external_source_change_conflict(self):
        r=work.open_page(self.project,1)
        newer=work.update(r['work'],element='body',changes={'content':{'text':'New'}})
        self.assertEqual('applied',newer['status']);before=self.sources()
        stale=work.update(r['work'],element='body',changes={'content':{'text':'Stale'}})
        self.assertEqual('conflict',stale['status']);self.assertEqual(before,self.sources())
        self.write('1.page.yaml',page(text='External'))
        self.assertEqual('conflict',work.update(newer['work'])['status'])
        self.assertIn('External',(self.project/'1.page.yaml').read_text())

    def test_render_failure_retains_candidate_and_matrix_then_retry_applies(self):
        r=work.open_page(self.project,1);before=self.sources()
        with patch('ansatz_slide.page_api.render_pptx',side_effect=RuntimeError('Office unavailable')):
            bad=work.update(r['work'],element='body',changes={'content':{'text':'New text'}})
        self.assertEqual('blocked',bad['status']);self.assertEqual(before,self.sources())
        self.assertEqual('passed',bad['candidates'][0]['geometry']['status'])
        self.assertEqual('applied',work.update(bad['work'])['status'])

    def test_create_failure_then_repair_publishes_formal_manifest(self):
        target=self.root/'new-deck'
        bad=work.create(target,self.settings,page(True))
        self.assertEqual('blocked',bad['status']);self.assertFalse((target/'pptx.yaml').exists())
        self.assertTrue(bad['candidates'][0]['geometry']['matrices'])
        good=work.update(bad['work'],element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('applied',good['status']);self.assertTrue((target/'pptx.yaml').exists())
        self.assertEqual('applied',work.update(good['work'],element='body',changes={'content':{'text':'Next'}})['status'])
        for path in target.glob('*.yaml'):
            text=path.read_text();self.assertTrue(text.startswith(SOURCE_HEADER))
            self.assertEqual(1,text.count(SOURCE_HEADER))
            parse_document(text,str(path))

    def test_outline_is_model_authored_and_invalidated_by_source_change(self):
        intent={'purpose':'Explain method','claim':'A test claim','evidence':['Figure 1'],'connection':'Supports the next result'}
        outline(self.project,1,intent)
        r=work.open_page(self.project,1)
        self.assertEqual(intent,r['context']['current']['intent']);self.assertFalse(r['context']['current']['needsReview'])
        r=work.update(r['work'],element='body',changes={'content':{'text':'Changed'}})
        self.assertTrue(r['context']['current']['needsReview'])
        self.assertEqual(intent,r['context']['current']['intent'])

    def test_split_failed_second_candidate_repair_and_continue(self):
        r=work.open_page(self.project,1)
        good=self.write('good.page.yaml',page());bad=self.write('bad.page.yaml',page(True))
        before=self.sources();failed=work.change(r['work'],'split',[good,bad])
        self.assertEqual('blocked',failed['status']);self.assertEqual(before,self.sources())
        fixed=work.update(failed['work'],candidate=2,element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('applied',fixed['status'],fixed['issues'])
        self.assertEqual(3,len(parse_document((self.project/'pptx.yaml').read_text(), "test source")['pages']))
        self.assertEqual('applied',work.update(fixed['work'],element='body',changes={'content':{'text':'After split'}})['status'])

    def test_move_remove_and_insert_from_work_references(self):
        r=work.open_page(self.project,1);other=work.open_page(self.project,2)
        moved=work.change(r['work'],'move',other=other['work'])
        self.assertEqual('applied',moved['status'],moved['issues']);self.assertEqual(2,moved['page'])
        removed=work.change(moved['work'],'remove');self.assertEqual('applied',removed['status'],removed['issues'])
        path=self.write('new.page.yaml',page())
        inserted=work.change(removed['work'],'insert',[path]);self.assertEqual('applied',inserted['status'],inserted['issues'])

    def test_new_cli_returns_json_for_blocked_and_repair(self):
        self.write('1.page.yaml',page(True))
        out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(io.StringIO()):
            code=main(['page','open',str(self.project),'--page','1'])
        self.assertEqual(1,code);bad=json.loads(out.getvalue());self.assertEqual('blocked',bad['status'])
        changes=self.write('changes.yaml',{'bounds':[1,8,8,3]});out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(io.StringIO()):
            code=main(['page','update',bad['work'],'--element','body','--changes',str(changes)])
        self.assertEqual(0,code);self.assertEqual('applied',json.loads(out.getvalue())['status'])

    def test_three_geometry_failures_freeze_content_and_suggest_split(self):
        self.write('1.page.yaml',page(True))
        first=work.open_page(self.project,1)
        self.assertEqual(1,first['candidates'][0]['geometryFailures'])
        rejected=work.update(first['work'],element='body',changes={'content':{'text':'Do not delete the evidence'}})
        self.assertTrue(rejected['rejectedChange'])
        self.assertEqual(first['work'],rejected['work'])
        self.assertEqual('Body',rejected['candidates'][0]['page']['elements'][1]['content']['text'])
        second=work.update(first['work'],element='body',changes={'bounds':[1,2.5,8,3]})
        third=work.update(second['work'],element='body',changes={'bounds':[1,3,8,3]})
        self.assertEqual(3,third['candidates'][0]['geometryFailures'])
        self.assertIn('consider splitting',third['candidates'][0]['guidance'])
        fixed=work.update(third['work'],element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('applied',fixed['status']);self.assertEqual(0,fixed['candidates'][0]['geometryFailures'])

    def test_blocked_page_can_split_without_content_loss(self):
        self.write('1.page.yaml',page(True));r=work.open_page(self.project,1)
        original=r['candidates'][0]['page']
        left=self.write('left.page.yaml',{'elements':[original['elements'][0]]})
        right=self.write('right.page.yaml',{'elements':[original['elements'][1]]})
        bad=self.write('empty.page.yaml',{'elements':[]})
        rejected=work.change(r['work'],'split',[left,bad])
        self.assertTrue(rejected['rejectedChange'])
        fixed=work.change(r['work'],'split',[left,right])
        self.assertEqual('applied',fixed['status'],fixed['issues'])
        self.assertEqual(3,len(parse_document((self.project/'pptx.yaml').read_text(), "test source")['pages']))

    def test_blocked_initial_page_can_split_before_manifest_creation(self):
        r=work.create(self.root/'fresh',self.settings,page(True))
        original=r['candidates'][0]['page']
        left=self.write('left.page.yaml',{'elements':[original['elements'][0]]})
        right=self.write('right.page.yaml',{'elements':[original['elements'][1]]})
        fixed=work.change(r['work'],'split',[left,right])
        self.assertEqual('applied',fixed['status'],fixed['issues'])
        self.assertEqual(2,len(parse_document((self.root/'fresh'/'pptx.yaml').read_text(), "test source")['pages']))

    def test_structural_failure_returns_matrix_of_other_blocking_page(self):
        self.write('2.page.yaml',page(True))
        r=work.open_page(self.project,1);new=self.write('insert.page.yaml',page())
        blocked=work.change(r['work'],'insert',[new])
        self.assertEqual('blocked',blocked['status'])
        self.assertEqual(2,blocked['blockingPages'][0]['page'])
        self.assertEqual(2,decode(blocked['blockingPages'][0]['geometry']['matrices'],'counts')[2][1])

    def test_three_page_logic_has_explicit_roles_and_separate_live_constraints(self):
        manifest=parse_document((self.project/'pptx.yaml').read_text(), "test source");manifest['pages'].append('3.page.yaml')
        self.write('pptx.yaml',manifest);self.write('3.page.yaml',page(text='PRIVATE_THIRD_BODY'))
        for number in (1,2,3):
            outline(self.project,number,{'purpose':f'Purpose {number}','claim':f'Claim {number}',
                'evidence':[f'Source {number}'],'previousConnection':f'From {number-1}',
                'nextConnection':f'To {number+1}','requirements':[f'Explain reasoning {number}'],
                'suggestions':[f'Consider example {number}']})
        r=work.open_page(self.project,2)
        for role,number in [('previous',1),('current',2),('next',3)]:
            self.assertEqual(number,r['context'][role]['page'])
            self.assertEqual(f'Claim {number}',r['context'][role]['intent']['claim'])
        self.assertNotIn('PRIVATE_THIRD_BODY',json.dumps(r))
        self.assertEqual(3,len(r['gates']['live']['requirements']))
        self.assertTrue(all(x['optional'] for x in r['gates']['live']['suggestions']))
        self.assertEqual('not evaluated by the CLI',r['gates']['live']['evaluation'])
        self.assertEqual([],r['gates']['hard']['blockingIssues'])

    def test_live_requirements_do_not_decide_program_acceptance(self):
        intent={'requirements':['Explain causation with evidence before drawing a conclusion'],
                'suggestions':['Consider splitting this page']}
        outline(self.project,1,intent)
        r=work.open_page(self.project,1)
        changed=work.update(r['work'],element='body',changes={'content':{'text':'A short draft'}})
        self.assertEqual('applied',changed['status'])
        self.assertEqual(intent['requirements'][0],changed['gates']['live']['requirements'][0]['text'])
        bad=work.update(changed['work'],element='body',changes={'bounds':[1,2,8,3]})
        self.assertEqual('blocked',bad['status'])
        self.assertTrue(bad['gates']['hard']['blockingIssues'])
        self.assertEqual('layout-only',bad['gates']['hard']['activeRestrictions'][0]['rule'])
        third=work.update(work.update(bad['work'])['work'])
        self.assertTrue(any(s.get('code')=='consider-split' and s['optional'] for s in third['gates']['live']['suggestions']))
        fixed=work.update(third['work'],element='body',changes={'bounds':[1,8,8,3]})
        self.assertEqual('applied',fixed['status'])  # Split is a suggestion, never required.

    def test_neighbor_changes_mark_relationship_for_model_review_without_blocking(self):
        outline(self.project,1,{'purpose':'Set up next page','nextConnection':'Explain the evidence next'})
        self.write('2.page.yaml',page(text='Revised neighbor'))
        r=work.open_page(self.project,1)
        self.assertTrue(r['context']['current']['relationNeedsReview'])
        self.assertEqual('ready',r['status'])
        self.assertIsNone(r['context']['previous'])
        last=work.open_page(self.project,2);self.assertIsNone(last['context']['next'])

    def test_live_metadata_rejects_malformed_lists_without_overwriting_outline(self):
        outline(self.project,1,{'purpose':'Keep this intent'})
        path=self.project/'.ansatz'/'outline.json';before=path.read_bytes()
        for value in [True,[1],[' ']]:
            with self.assertRaises(ValueError):outline(self.project,1,{'requirements':value})
            self.assertEqual(before,path.read_bytes())
