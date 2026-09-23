"""Model-authored page intent, with source-version freshness instead of semantic claims."""
import json
from . import page_api as api
from .project import atomic_write
from . import narrative

TEXT_FIELDS={'purpose','claim','connection','previousConnection','nextConnection'}
LIST_FIELDS={'evidence','requirements','suggestions'}
FIELDS=TEXT_FIELDS|LIST_FIELDS


def neighbors(snap,number):
    return {key:({'source':snap['manifest']['pages'][i-1],
                  'dependencyToken':api.presentation_token(snap,i)}
                 if 1<=i<=len(snap['pages']) else None)
            for key,i in [('previous',number-1),('next',number+1)]}


def read(snap):
    folder=api.session_path(snap['root']/'.ansatz')
    path=folder/'outline.json'
    return json.loads(path.read_text()) if path.exists() else {'format':1,'pages':{}}


def entry(snap,number,data=None,narrative_data=None):
    data=read(snap) if data is None else data
    name=snap['manifest']['pages'][number-1]
    item=data['pages'].get(name)
    narrative_data=narrative.read(snap) if narrative_data is None else narrative_data
    brief_token=narrative.brief_token(narrative_data,[name])
    premise_changed=bool(item) and item.get('briefToken')!=brief_token
    relation_changed=item is None or item.get('neighbors')!=neighbors(snap,number)
    return {'page':number,'source':name,'title':api.title(snap['pages'][number-1]),
            'intent':item['intent'] if item else None,
            'relationNeedsReview':relation_changed,'briefNeedsReview':premise_changed,
            'origin':'model','requirementsKind':'model_proposal',
            'needsReview':item is None or premise_changed or relation_changed or item.get('dependencyToken')!=api.presentation_token(snap,number)}


def context(snap,number):
    data=read(snap);narrative_data=narrative.read(snap)
    previous=entry(snap,number-1,data,narrative_data) if number>1 else None
    following=entry(snap,number+1,data,narrative_data) if number<len(snap['pages']) else None
    return {'previous':previous,'current':entry(snap,number,data,narrative_data),'next':following,
            'narrative':narrative.view(snap,number,narrative_data),
            'meaning':'Intent is model-authored. needsReview detects source changes, not semantic correctness.'}


def outline(project,number=None,intent=None):
    snap=api.snapshot(project)
    if intent is not None:
        if number is None or not 1<=number<=len(snap['pages']):raise ValueError('Outline update requires an existing --page')
        if not isinstance(intent,dict) or set(intent)-FIELDS:raise ValueError('Intent fields: '+', '.join(sorted(FIELDS)))
        if any(not isinstance(intent.get(k,''),str) for k in TEXT_FIELDS):raise ValueError('Intent text fields must be strings')
        for key in LIST_FIELDS:
            if key in intent and (not isinstance(intent[key],list) or any(not isinstance(x,str) or not x.strip() for x in intent[key])):
                raise ValueError(key+' must be a list of nonempty text descriptions')
        folder=api.session_path(snap['root']/'.ansatz');folder.mkdir(exist_ok=True)
        with api.lock(folder/'.outline.lock'):
            data=read(snap);name=snap['manifest']['pages'][number-1]
            data['pages'][name]={'intent':intent,'dependencyToken':api.presentation_token(snap,number),
                                 'neighbors':neighbors(snap,number),'briefToken':narrative.brief_token(narrative.read(snap),[name])}
            if not api.unchanged(snap['tracked']):raise RuntimeError('Source changed while recording intent; reread outline')
            atomic_write(folder/'outline.json',api.json_bytes(data),force=True)
    data=read(snap);narrative_data=narrative.read(snap)
    return {'status':'applied' if intent is not None else 'ready','project':str(snap['manifestPath']),
            'narrative':narrative.view(snap,data=narrative_data),
            'pages':[entry(snap,i,data,narrative_data) for i in range(1,len(snap['pages'])+1)],
            'retiredSources':[name for name in data['pages'] if name not in snap['manifest']['pages']]}
