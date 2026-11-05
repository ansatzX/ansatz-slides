"""Attribution lifecycle and whole-deck context; no semantic grading is inferred."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ansatz_slide import narrative, work_objects as work
from ansatz_slide import narrative as outline
from ansatz_slide.cli import main
from .test_page_api import fake_render


class NarrativeTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[2]/'tmp/test-tmp';base.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.order=['a.page.yaml','b.page.yaml','c.page.yaml']
        self.write('pptx.yaml',{'version':'v2','size':[960,540],'pages':self.order})
        for n in self.order:self.write(n,{'elements':[{'elementId':'title','elementType':'text','bounds':[20,20,600,60],'content':{'text':n,'fontSize':24}}]})
        self.brief={'purpose':'Explain the evidence','audience':'Researchers','centralClaim':'Claim is conditional',
            'sections':[{'id':n[0],'claim':'Role '+n[0],'sources':[n]} for n in self.order]}
        for target,value in [('ansatz_slide.page_api.checks.render_pptx',fake_render),('ansatz_slide.page_api.checks.measure_text',None)]:
            mock=patch(target,side_effect=value) if value else patch(target,return_value={'status':'passed','elements':[]})
            mock.start();self.addCleanup(mock.stop)

    def write(self,name,value):
        path=self.root/name;path.write_text(json.dumps(value));return path

    def directive(self,ident='keep-limit',kind='user_requirement',scope=None):
        return {'id':ident,'kind':kind,'text':'Keep the limitation','scope':scope or ['a.page.yaml'],
                'source':{'reference':'conversation:actual-source-reference','quote':'Keep the limitation'}}

    def test_current_context_distinguishes_user_model_and_program(self):
        narrative.save(self.root,'brief',self.brief)
        narrative.save(self.root,'directive',self.directive())
        narrative.save(self.root,'directive',self.directive('plan','model_proposal'))
        outline.outline(self.root,1,{'claim':'Conditional result','requirements':['Explain method']})
        result=work.open_page(self.root,1)
        self.assertEqual(self.brief,result['context']['narrative']['brief']['content'])
        self.assertEqual('user_requirement',result['gates']['live']['userRequirements'][0]['kind'])
        self.assertTrue(all(x['kind']=='model_proposal' for x in result['gates']['live']['modelProposals']))
        self.assertEqual('program',result['gates']['facts']['origin'])
        self.assertEqual('ready',result['status'])
        self.assertFalse(result['context']['current']['needsReview'])

    def test_revoke_preserves_history_and_disappears_on_next_work(self):
        directive=self.directive();narrative.save(self.root,'directive',directive)
        opened=work.open_page(self.root,1)
        narrative.save(self.root,'revoke',{'id':directive['id'],'reference':'conversation:revocation','quote':'Remove that requirement'})
        result=work.update(opened['work'],element='title',changes={'content':{'text':'Updated'}})
        self.assertTrue(result['applied'])
        self.assertEqual([],result['gates']['live']['userRequirements'])
        data=narrative.inspect(self.root,history=True)
        self.assertEqual('revoked',data['history'][-1]['after']['status'])
        self.assertEqual('active',data['history'][-1]['before']['status'])
        self.assertNotIn('history',narrative.inspect(self.root))

    def test_source_change_marks_only_dependent_directives_and_sections(self):
        narrative.save(self.root,'brief',self.brief)
        narrative.save(self.root,'directive',self.directive())
        narrative.save(self.root,'directive',self.directive('other',scope=['c.page.yaml']))
        self.write('a.page.yaml',{'elements':[]})
        state=narrative.inspect(self.root)
        self.assertEqual(['a'],state['brief']['sectionsNeedingReview'])
        self.assertEqual([True,False],[d['needsReview'] for d in state['userRequirements']])
        self.assertTrue(all(d['status']=='active' for d in state['userRequirements']))

    def test_structure_change_and_core_premise_change_request_review(self):
        narrative.save(self.root,'brief',self.brief)
        for i in (1,2,3):outline.outline(self.root,i,{'claim':'Current'})
        altered=copy.deepcopy(self.brief);altered['sections'][0]['claim']='New role'
        narrative.save(self.root,'brief',altered)
        entries=outline.outline(self.root)['pages']
        self.assertEqual([True,False,False],[e['briefNeedsReview'] for e in entries])
        altered['centralClaim']='New central claim';narrative.save(self.root,'brief',altered)
        self.assertTrue(all(e['briefNeedsReview'] for e in outline.outline(self.root)['pages']))
        self.write('pptx.yaml',{'version':'v2','size':[960,540],'pages':list(reversed(self.order))})
        self.assertTrue(narrative.inspect(self.root)['brief']['structureNeedsReview'])

    def test_reaffirming_same_brief_does_not_invalidate_page_intent(self):
        narrative.save(self.root,'brief',self.brief);outline.outline(self.root,1,{'claim':'Current'})
        narrative.save(self.root,'brief',self.brief)
        self.assertFalse(outline.outline(self.root)['pages'][0]['needsReview'])

    def test_invalid_attribution_or_scope_does_not_replace_state(self):
        narrative.save(self.root,'directive',self.directive())
        before=(self.root/'.ansatz/narrative.json').read_bytes()
        for key,value in [('kind','program_fact'),('source',{}),('scope',['missing.page.yaml'])]:
            bad=self.directive();bad[key]=value
            with self.assertRaises(ValueError):narrative.save(self.root,'directive',bad)
        with self.assertRaises(ValueError):narrative.save(self.root,'directive',self.directive(kind='model_proposal'))
        self.assertEqual(before,(self.root/'.ansatz/narrative.json').read_bytes())

    def test_cli_writes_reads_and_revokes_with_source(self):
        from contextlib import redirect_stdout
        from io import StringIO
        path=self.write('directive-input.json',self.directive())
        with redirect_stdout(StringIO()) as out:
            code=main(['deck','directive',str(self.root),'--content',str(path)])
        self.assertEqual(0,code);self.assertEqual('active',json.loads(out.getvalue())['userRequirements'][0]['status'])
        with redirect_stdout(StringIO()) as out:
            code=main(['deck','directive',str(self.root),'--revoke','keep-limit','--source','conversation:next','--quote','Drop it'])
        self.assertEqual(0,code);self.assertEqual([],json.loads(out.getvalue())['userRequirements'])

    def test_removed_scope_is_visible_until_explicitly_resolved(self):
        narrative.save(self.root,'directive',self.directive())
        self.write('pptx.yaml',{'version':'v2','size':[960,540],'pages':self.order[1:]})
        result=work.open_page(self.root,1)
        pending=result['gates']['live']['unresolvedDirectives']
        self.assertEqual('keep-limit',pending[0]['id'])
        self.assertEqual('active',pending[0]['status'])
        self.assertTrue(pending[0]['scopeNeedsReview'])

    def test_stale_work_does_not_revive_a_revoked_requirement(self):
        narrative.save(self.root,'directive',self.directive())
        opened=work.open_page(self.root,1)
        narrative.save(self.root,'revoke',{'id':'keep-limit','reference':'conversation:new','quote':'Revoke it'})
        self.write('a.page.yaml',{'elements':[]})
        result=work.update(opened['work'],element='title',changes={'content':{'text':'New'}})
        self.assertEqual('conflict',result['status'])
        self.assertEqual([],result['gates']['live']['userRequirements'])
        self.assertEqual('historical',result['gates']['facts']['state'])
