"""Current deck argument and attributed directives, with durable revision history.

Attribution records evidence supplied by the caller; it does not authenticate a
human or turn semantic requirements into program-enforced publication gates.
"""
import copy
import json
from . import page_api as api
from .project import atomic_write


def read(snap):
    path=api.session_path(snap['root']/'.ansatz')/'narrative.json'
    return json.loads(path.read_text()) if path.exists() else {'format':1,'revision':0,'brief':None,'directives':{},'history':[]}


def text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+' must be nonempty text')


def sources(value,snap):
    if not isinstance(value,list) or not value or any(not isinstance(x,str) for x in value):
        raise ValueError('sources must be a nonempty list of source page filenames')
    if len(set(value))!=len(value) or any(x not in snap['manifest']['pages'] for x in value):
        raise ValueError('sources must contain unique current source page filenames')


def tokens(snap,names):
    order=snap['manifest']['pages']
    return {name:api.presentation_token(snap,order.index(name)+1) if name in order else None for name in names}


def brief_token(data,names=None):
    if not data['brief']:return None
    content=copy.deepcopy(data['brief']['content'])
    if names is not None:
        content['sections']=[section for section in content['sections'] if any(n in names for n in section['sources'])]
    return api.sha(api.json_bytes(content))


def brief_view(snap,data):
    saved=data['brief']
    if saved is None:return {'status':'missing','needsReview':True,'content':None}
    changed=[name for name,value in saved['dependencies'].items() if tokens(snap,[name])[name]!=value]
    order_changed=saved['order']!=snap['manifest']['pages']
    return {'status':'current','origin':'model','revision':saved['revision'],'content':saved['content'],
            'needsReview':bool(changed or order_changed),'changedSources':changed,
            'structureNeedsReview':order_changed,
            'sectionsNeedingReview':[s['id'] for s in saved['content']['sections'] if order_changed or any(n in changed for n in s['sources'])],
            'evaluation':'Source freshness only; argument quality is not evaluated by the program'}


def directive_view(snap,item,brief_revision):
    dependencies=tokens(snap,list(item['dependencies']))
    changed=[name for name,value in item['dependencies'].items() if dependencies[name]!=value]
    structure=item['scope']=='deck' and item['order']!=snap['manifest']['pages']
    premise=item['briefRevision']!=brief_revision
    return {k:copy.deepcopy(item[k]) for k in ('id','kind','text','source','scope','status','revision')} | {
        'needsReview':bool(changed or structure or premise),'changedSources':changed,
        'scopeNeedsReview':item['scope']!='deck' and any(n not in snap['manifest']['pages'] for n in item['scope']),
        'structureNeedsReview':structure,'briefNeedsReview':premise,
        'attributionVerification':'not authenticated by CLI; caller must preserve the cited source'}


def view(snap,number=None,data=None):
    data=read(snap) if data is None else data
    brief=brief_view(snap,data)
    name=snap['manifest']['pages'][number-1] if number else None
    active=[directive_view(snap,d,brief_token(data,None if d['scope']=='deck' else d['scope'])) for d in data['directives'].values()
            if d['status']=='active' and (name is None or d['scope']=='deck' or name in d['scope'])]
    unresolved=[directive_view(snap,d,brief_token(data,d['scope'])) for d in data['directives'].values()
                if d['status']=='active' and d['scope']!='deck' and any(n not in snap['manifest']['pages'] for n in d['scope'])]
    return {'revision':data['revision'],'brief':brief,'unresolvedDirectives':unresolved,
            'userRequirements':[d for d in active if d['kind']=='user_requirement'],
            'modelProposals':[d for d in active if d['kind']=='model_proposal'],
            'historyPath':str(snap['root']/'.ansatz/narrative.json'),
            'meaning':'Active directives only. A changed source requests review; it does not revoke a user requirement. Model proposals are revisable.'}


def save(project,operation,payload):
    snap=api.snapshot(project)
    folder=api.session_path(snap['root']/'.ansatz');folder.mkdir(exist_ok=True)
    with api.lock(folder/'.narrative.lock'):
        data=read(snap);revision=data['revision']+1
        if operation=='brief':
            if not isinstance(payload,dict) or set(payload)!={'purpose','audience','centralClaim','sections'}:
                raise ValueError('Brief requires purpose, audience, centralClaim and sections')
            for key in ('purpose','audience','centralClaim'):text(payload[key],key)
            if not isinstance(payload['sections'],list) or not payload['sections']:raise ValueError('sections must be a nonempty list')
            ids=[]
            for section in payload['sections']:
                if not isinstance(section,dict) or set(section)!={'id','claim','sources'}:raise ValueError('Each section requires id, claim and sources')
                for key in ('id','claim'):text(section[key],key)
                sources(section['sources'],snap);ids.append(section['id'])
            if len(set(ids))!=len(ids):raise ValueError('Section IDs must be unique')
            before=data['brief'];names=list(dict.fromkeys(n for s in payload['sections'] for n in s['sources']))
            # Every existing page must have a role in the whole-deck argument.
            if set(names)!=set(snap['manifest']['pages']):raise ValueError('Brief sections must cover every current source page')
            after={'revision':revision,'content':payload,'order':snap['manifest']['pages'],'dependencies':tokens(snap,names)}
            data['brief']=after
        elif operation=='directive':
            if not isinstance(payload,dict) or set(payload)!={'id','kind','text','source','scope'}:raise ValueError('Directive requires id, kind, text, source and scope')
            for key in ('id','text'):text(payload[key],key)
            if payload['kind'] not in ('user_requirement','model_proposal'):raise ValueError('Only user_requirement or model_proposal can be authored; measurements come from the program')
            source=payload['source']
            if not isinstance(source,dict) or set(source)!={'reference','quote'}:raise ValueError('source requires reference and quote')
            for key in source:text(source[key],'source.'+key)
            scope=payload['scope']
            if scope!='deck':sources(scope,snap)
            before=data['directives'].get(payload['id'])
            if before and before['kind']!=payload['kind']:raise ValueError('A directive cannot change origin kind; use a new ID')
            after={**payload,'status':'active','revision':revision,'dependencies':tokens(snap,snap['manifest']['pages'] if scope=='deck' else scope),
                   'order':snap['manifest']['pages'],'briefRevision':brief_token(data,None if scope=='deck' else scope)}
            data['directives'][payload['id']]=after
        elif operation=='revoke':
            ident=payload['id'];text(payload['reference'],'revocation source');text(payload['quote'],'revocation quote')
            if ident not in data['directives']:raise ValueError('Unknown directive ID')
            before=data['directives'][ident]
            after={**before,'status':'revoked','revision':revision,'revocationSource':{'reference':payload['reference'],'quote':payload['quote']}}
            data['directives'][ident]=after
        else:raise ValueError('Unknown narrative operation')
        data['history'].append({'revision':revision,'operation':operation,'before':before,'after':copy.deepcopy(after)})
        data['revision']=revision
        if not api.unchanged(snap['tracked']):raise RuntimeError('Source changed while recording narrative; reread current project')
        atomic_write(folder/'narrative.json',api.json_bytes(data),force=True)
    return {'status':'applied','project':str(snap['manifestPath']),**view(snap,data=data)}


def inspect(project,history=False):
    snap=api.snapshot(project);data=read(snap)
    result={'status':'ready','project':str(snap['manifestPath']),**view(snap,data=data)}
    if history:result['history']=data['history']
    return result
