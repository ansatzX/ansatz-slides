"""Describe program-enforced constraints separately from model judgment.

This module annotates responses only. Live requirements never set result status
or authorize a write; the execution layer remains responsible for hard gates.
"""


def attach(result):
    context=result.setdefault('context',{})
    context.setdefault('previous',None);context.setdefault('current',None);context.setdefault('next',None)
    requirements=[];suggestions=[]
    for role in ('previous','current','next'):
        entry=context.get(role)
        if not entry:continue
        intent=entry.get('intent') or {}
        source={'role':role,'page':entry['page'],'source':entry['source'],
                'needsReview':entry.get('needsReview',True),'origin':'model-authored outline','kind':'model_proposal','status':'active'}
        requirements.extend({**source,'text':text} for text in intent.get('requirements',[]))
        suggestions.extend({**source,'text':text} for text in intent.get('suggestions',[]))
    narrative=context.get('narrative') or {}
    user_requirements=narrative.get('userRequirements',[])
    model_proposals=requirements+narrative.get('modelProposals',[])
    restrictions=[]
    for candidate in result.get('candidates',[]):
        if candidate.get('layoutOnly'):
            restrictions.append({'candidate':candidate['index'],'rule':'layout-only',
                'allowedChanges':['bounds','rotation','element order'],
                'preserve':['content','styles','elements','overlap declarations']})
        if candidate.get('geometryFailures',0)>=3:
            suggestions.append({'candidate':candidate['index'],'origin':'geometry retry count',
                'code':'consider-split','optional':True,
                'text':'Three consecutive geometry checks failed. The page may be too crowded; consider a content-preserving split. Further layout repair is also allowed.'})
    result['gates']={
        'hard':{'owner':'program','rules':['source version and edit scope','schema and resources',
                                         'geometry bounds and declared overlaps','layout-only repair after geometry failure',
                                         'measured native text must fit its frame','successful rendering before source publication'],
                'blockingIssues':result.get('issues',[]) if not result.get('applied') else [],
                'activeRestrictions':restrictions,'applied':result.get('applied')},
        'live':{'owner':'model','requirements':requirements+user_requirements,
                'userRequirements':user_requirements,'modelProposals':model_proposals,
                'unresolvedDirectives':narrative.get('unresolvedDirectives',[]),
                'suggestions':[{**s,'optional':True} for s in suggestions],
                'evaluation':'not evaluated by the CLI',
                'instruction':'Honor semantic requirements using the three-page logic and evidence. Suggestions are optional. Program success is not semantic acceptance.'}}
    result['gates']['visual']={'owner':'model','status':'not_evaluated',
        'instruction':'Open the actual PPTX render to assess typography, hierarchy, crops and readability. Geometry/text-fit passes and successful rendering do not constitute visual acceptance.'}
    result['gates']['facts']={'origin':'program','work':result.get('work'),
        'state':'historical' if result.get('status')=='conflict' else 'candidate',
        'applied':result.get('applied',False),
        'evidenceFields':['candidates[].geometry','textFit'],
        'meaning':'Measured/schema/geometry facts only; no semantic acceptance. Evidence belongs to this work candidate; failed publication does not update formal sources.'}
    return result
