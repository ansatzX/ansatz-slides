"""Revision-bound page work objects: candidate, evidence and one next operation."""
import copy
import json
from pathlib import Path
import uuid

from . import page_api as api
from . import outline
from .occupancy import write_precheck, matrix_payload, require_pass
from .project import atomic_write, parse_document, source_bytes, manifest_paths
from .validation import validate_project
from .gates import attach as attach_gates


def _content_signature(page):
    value=copy.deepcopy(page)
    for element in value.get('elements',[]):
        element.pop('bounds',None);element.pop('rotation',None)
    value['elements']=sorted(value.get('elements',[]),key=lambda e:e['elementId'])
    return api.json_bytes(value)


def _refresh_narrative(result):
    # Rejected/stale work may carry historical evidence, but must not revive a
    # directive revoked since that evidence was generated.
    from . import narrative
    try:
        snap=api.snapshot(result['project'])
        number=min(result['page'],len(snap['pages']))
        result.setdefault('context',{})['narrative']=narrative.view(snap,number)
    except Exception as exc:
        result.setdefault('context',{})['narrative']={'status':'unavailable','needsReview':True,
            'reason':str(exc),'userRequirements':[],'modelProposals':[],
            'meaning':'Current directives could not be read; do not infer that no requirements apply. Reopen the project.'}
    return result


def _layout_rejection(work,message):
    result=json.loads((work/'result.json').read_text())
    return attach_gates(_refresh_narrative({**result,'status':'blocked','applied':False,
            'issues':result['issues']+[{'kind':'layout-only','message':message}],
            'rejectedChange':True}))


def _split_preserves_content(originals,candidates):
    # Redistribute elements; do not erase/rewrite content to silence a geometry gate.
    def elements(pages):
        result=[]
        for page in pages:
            for element in page.get('elements',[]):
                element=copy.deepcopy(element)
                element.pop('bounds',None);element.pop('rotation',None)
                result.append(api.json_bytes(element))
        return sorted(result)
    if elements(originals)!=elements(candidates):return False
    original_notes=[p.get('notes','') for p in originals if p.get('notes')]
    candidate_notes=[p.get('notes','') for p in candidates if p.get('notes')]
    return original_notes==candidate_notes


def _new(folder):
    path=folder/uuid.uuid4().hex;path.mkdir(parents=True)
    return path


def _root(project):
    folder=api.session_path(Path(project)/'.ansatz'/'work')
    folder.mkdir(parents=True,exist_ok=True)
    return _new(folder)


def _read(work):
    work=api.session_path(work)
    record=json.loads((work/'record.json').read_text())
    if record.get('format')!=1:raise ValueError('Unsupported page work format')
    return work,record


def _finish(work,record,result):
    result={'format':'page-work-v1','work':str(work),**result}
    attach_gates(result)
    result['next']={'command':['ansatz-slide','page','update',str(work)],
                    'hint':'Modify a candidate with --element ID --changes FILE or --content FILE; no arguments retries the retained candidate.'}
    atomic_write(work/'record.json',api.json_bytes(record))
    atomic_write(work/'result.json',api.json_bytes(result))
    api.session_path(work.parent)
    atomic_write(work.parent/'head.json',api.json_bytes({'work':str(work)}),force=True)
    return result


def _conflict(work,record,message):
    previous=json.loads((work/'result.json').read_text())
    for role in ('previous','current','next'):
        item=previous.get('context',{}).get(role)
        if item:item['needsReview']=True
    return attach_gates(_refresh_narrative({**previous,'status':'conflict','applied':False,'issues':[{'kind':'conflict','message':message}],
            'next':{'command':['ansatz-slide','page','open',record['project'],'--page',str(record['page'])],
                    'hint':'Reread current source. This work and its candidate remain available; no automatic overwrite.'}}))


def _current(work,record):
    head=json.loads((work.parent/'head.json').read_text())
    if head['work']!=str(work):raise ValueError('This work reference was superseded; use the work returned by the last operation')
    if record['operation']['kind']=='create':
        if manifest_paths(record['project']):raise ValueError('Project was already created')
        return None
    snap=api.snapshot(record['project'])
    if record['baseToken']!=api.page_token(snap,record['page']):raise ValueError('Source or related assets changed after this work was opened')
    return snap


def _candidates(work,record,snap):
    results=[];issues=[]
    size=record['settings']['size'] if snap is None else snap['manifest']['size']
    root=Path(record['project']) if snap is None else snap['root']
    for i,candidate in enumerate(record['candidates'],1):
        path=work/f'candidate-{i}.page.yaml';atomic_write(path,api.json_bytes(candidate))
        item={'index':i,'page':candidate,'editable':str(path),'geometry':None,'preview':None}
        try:
            geometry=write_precheck(size,candidate,work/f'geometry-{i}')
            geometry['matrices']=matrix_payload(geometry)
            item['geometry']=geometry
        except Exception as exc:
            issues.append({'candidate':i,'kind':'geometry-input','message':str(exc)})
        try:
            manifest={**(record['settings'] if snap is None else snap['manifest']),'pages':[str(path.relative_to(root))]}
            validate_project(manifest,[candidate],root)
        except Exception as exc:
            issues.append({'candidate':i,'kind':'schema','message':str(exc)})
        if item['geometry'] is not None and item['geometry']['status']=='blocked':
            try:require_pass(item['geometry'])
            except ValueError as exc:issues.append({'candidate':i,'kind':'geometry','message':str(exc)})
        results.append(item)
    return results,issues


def _adapter(work,record,snap):
    """Keep existing source transaction guarantees behind the new interface."""
    session=work/'adapter';session.mkdir()
    original=snap['pages'][record['page']-1]
    state={'format':1,'project':str(snap['manifestPath']),'page':record['page'],
           'token':record['baseToken'],'width':record['width'],'draftHash':api.sha(api.json_bytes(original))}
    api.session_write(session,'page.page.yaml',api.json_bytes(original))
    api.session_write(session,'session.json',api.json_bytes(state))
    return session


def _execute(work,record,snap,items):
    operation=record['operation'];kind=operation['kind']
    if kind=='create':
        root=Path(record['project']);manifest={**record['settings'],'pages':[str(Path(item['editable']).relative_to(root)) for item in items]}
        fake={'manifest':manifest,'pages':record['candidates'],'root':root,'tracked':{}}
        rendered=[api.preview(fake,i,candidate,work,record['width']) for i,candidate in enumerate(record['candidates'],1)]
        assets = {}
        for evidence in rendered:
            for path, digest in evidence['_assetHashes'].items():
                if path in assets and assets[path] != digest:
                    raise RuntimeError('Assets changed between page previews; retry creation')
                assets[path] = digest
        with api.lock(root/'.ansatz-page-edit.lock'):
            if manifest_paths(root):raise ValueError('Project already has a manifest')
            if not api.unchanged(assets):raise RuntimeError('Assets changed after preview; retry creation')
            names=[f'page-{uuid.uuid4().hex}.page.yaml' for _ in items]
            for name,candidate in zip(names,record['candidates']):atomic_write(root/name,source_bytes(api.json_bytes(candidate)))
            manifest_path=root/'pptx.yaml'
            data=source_bytes(api.json_bytes({**record['settings'],'pages':names}))
            if manifest_paths(root) or not api.unchanged(assets):
                raise RuntimeError('Project or assets changed before publication; retry creation')
            atomic_write(manifest_path,data)
            try:
                if manifest_paths(root)!=[manifest_path] or not api.unchanged(assets):
                    raise RuntimeError('Project or assets changed during publication; retry creation')
            except Exception:
                from .file_transactions import retract_created
                retract_created(manifest_path,api.sha(data))
                raise
        return {'page':1,'textFit':[r['typography'] for r in rendered],'newPages':[{'page':i,'image':str(work/r['image']),'previewPptx':str(work/r['previewPptx'])} for i,r in enumerate(rendered,1)]}
    session=_adapter(work,record,snap);token=record['baseToken']
    contents=[Path(item['editable']) for item in items]
    if kind=='edit':return api.edit_page(session,token,contents[0])
    if kind in ('insert','split','merge','move','remove'):
        other_session=None;other_token=None
        if kind in ('merge','move'):
            other_work,other=_read(operation['other'])
            other_snap=_current(other_work,other)
            if other['project']!=record['project']:raise ValueError('Other work belongs to a different project')
            if json.loads((other_work/'result.json').read_text())['status'] not in ('ready','applied'):
                raise ValueError('Other work has a pending candidate; resolve it first')
            other_session=_adapter(_new(work),other,other_snap);other_token=other['baseToken']
        if kind in ('split','merge'):
            return api.reshape_pages(session,token,contents,other_session,other_token)
        return api.change_order(session,token,kind,content=contents[0] if kind=='insert' else None,
                                position=operation.get('position','after'),anchor_session=other_session,anchor_token=other_token)
    raise ValueError('Unknown work operation')


def _process(work,record,snap,*,apply):
    items,issues=_candidates(work,record,snap)
    previous=record.get('geometryFailures',[0]*len(items))
    failures=[]
    for i,item in enumerate(items):
        count=previous[i] if i<len(previous) else 0
        geometry=item['geometry']
        if geometry is not None:count=count+1 if geometry['status']=='blocked' else 0
        failures.append(count)
        item['geometryFailures']=count
        item['layoutOnly']=count>0
        item['guidance']=('Only change bounds/rotation; preserve content, styles and elements.' if count else '')
        if count>=3:
            item['guidance']+=' Three consecutive geometry checks failed. The page may be too crowded; consider splitting it while retaining all content.'
    record['geometryFailures']=failures
    result={'status':'blocked' if issues else 'ready','applied':False,
            'project':record['project'],'page':record['page'],'operation':record['operation'],
            'candidates':items,'issues':issues,
            'context':outline.context(snap,record['page']) if snap is not None else {'previous':None,'current':None,'next':None}}
    if not issues:
        try:
            if apply:
                outcome=_execute(work,record,snap,items)
                result.update(status='applied',applied=True)
                result['textFit']=outcome.get('textFit',[outcome.get('typography')])
                project=Path(record['project'])/'pptx.yaml' if snap is None else snap['manifestPath']
                updated=api.snapshot(project)
                number=outcome.get('page',outcome.get('newPages',[{'page':record['page']}])[0]['page'])
                record.update(project=str(project),page=number,baseToken=api.page_token(updated,number),
                              operation={'kind':'edit'},candidates=[updated['pages'][number-1]],geometryFailures=[0])
                result.update(status='applied',applied=True,project=str(project),page=number,
                              context=outline.context(updated,number),
                              effect={key:outcome[key] for key in ('changedPages','replacedPages','retiredSources',
                                      'removedSource','recoverySource','recoveryManifest','pageCount') if key in outcome})
                if 'newPages' in outcome:
                    for item,preview in zip(items,outcome['newPages']):
                        item['preview']={'image':preview['image'],'pptx':preview['previewPptx']}
                elif outcome.get('image'):
                    items[0]['preview']={'image':outcome['image'],'pptx':outcome['previewPptx']}
                # The returned primary candidate always matches the next operation.
                if len(items)!=1 or items[0]['page']!=record['candidates'][0]:
                    result['operationCandidates']=items
                    if items[0]['page']==record['candidates'][0]:result['candidates']=[items[0]]
                    else:
                        after=_new(work)
                        current_items,current_issues=_candidates(after,record,updated)
                        result['candidates']=current_items;result['issues'].extend(current_issues)
                        rendered=api.preview(updated,number,record['candidates'][0],after,record['width'])
                        current_items[0]['preview']={'image':str(after/rendered['image']) if rendered['image'] else None,
                                                     'pptx':str(after/rendered['previewPptx']) if rendered['previewPptx'] else None}
            else:
                rendered=api.preview(snap,record['page'],record['candidates'][0],work,record['width'])
                result['textFit']=[rendered['typography']]
                items[0]['preview']={'image':str(work/rendered['image']) if rendered['image'] else None,
                                     'pptx':str(work/rendered['previewPptx']) if rendered['previewPptx'] else None}
        except Exception as exc:
            if hasattr(exc,'report'):result['textFit']=[exc.report]
            if not result['applied']:
                result['status']='conflict' if 'concurrent' in str(exc).lower() or 'changed' in str(exc).lower() or 'stale' in str(exc).lower() else 'blocked'
            result['issues'].append({'kind':'execution','message':str(exc)})
            if not result['applied'] and snap is not None and 'Geometry precheck failed' in str(exc):
                from .occupancy import analyze
                result['blockingPages']=[]
                for number,page in enumerate(snap['pages'],1):
                    report,_=analyze(snap['manifest']['size'],page)
                    if report['status']=='blocked':
                        report=write_precheck(snap['manifest']['size'],page,work/f'blocking-page-{number}')
                        report['matrices']=matrix_payload(report)
                        result['blockingPages'].append({'page':number,'source':str(snap['paths'][number-1]),'geometry':report})
    return _finish(work,record,result)


def open_page(project,number,width=1600):
    if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
    snap=api.snapshot(project)
    if not 1<=number<=len(snap['pages']):raise ValueError('Page out of range')
    root=_root(snap['root']);work=_new(root)
    record={'format':1,'project':str(snap['manifestPath']),'page':number,'width':width,
            'baseToken':api.page_token(snap,number),'operation':{'kind':'edit'},
            'candidates':[snap['pages'][number-1]]}
    return _process(work,record,snap,apply=False)


def update(work,content=None,element=None,changes=None,candidate=1):
    work,record=_read(work)
    with api.lock(work.parent/'.work.lock'):
        try:snap=_current(work,record)
        except Exception as exc:return _conflict(work,record,str(exc))
        record=copy.deepcopy(record)
        if not 1<=candidate<=len(record['candidates']):raise ValueError('Candidate index out of range')
        if content is not None and element is not None:raise ValueError('Choose full content or one element update')
        original=record['candidates'][candidate-1]
        if content is not None:record['candidates'][candidate-1]=parse_document(Path(content).read_text(),str(content))
        elif element is not None:
            record['candidates'][candidate-1]=api.patch_element(record['candidates'][candidate-1],element,changes)
        failures=record.get('geometryFailures',[])
        if candidate<=len(failures) and failures[candidate-1]>0:
            if _content_signature(original)!=_content_signature(record['candidates'][candidate-1]):
                return _layout_rejection(work,'After geometry failure, only bounds/rotation and element ordering may change. Content, styles and elements are frozen; rejected input did not replace the retained candidate.')
        return _process(_new(work.parent),record,snap,apply=True)


def change(work,kind,contents=(),other=None,position='after'):
    work,record=_read(work)
    with api.lock(work.parent/'.work.lock'):
        try:snap=_current(work,record)
        except Exception as exc:return _conflict(work,record,str(exc))
        pending=json.loads((work/'result.json').read_text())['status'] not in ('ready','applied')
        repair_split=(kind=='split' and record['operation']['kind'] in ('edit','create') and any(record.get('geometryFailures',[])))
        if pending and not repair_split:
            return attach_gates({**json.loads((work/'result.json').read_text()),'issues':[{'kind':'pending','message':'Repair or reopen this pending candidate before changing page structure'}]})
        record=copy.deepcopy(record)
        creating=record['operation']['kind']=='create'
        originals=record['candidates']
        record['operation']={'kind':'create' if creating else kind,'position':position,'other':str(other) if other else None}
        if kind in ('insert','split','merge'):
            expected=2 if kind=='split' else 1
            if len(contents)<expected or (kind!='split' and len(contents)!=1):raise ValueError('Wrong candidate count')
            record['candidates']=[parse_document(Path(p).read_text(),str(p)) for p in contents]
        if repair_split and not _split_preserves_content(originals,record['candidates']):
            return _layout_rejection(work,'Repair split must redistribute existing elements and preserve their content/styles and notes; do not remove or rewrite content to pass geometry.')
        record['geometryFailures']=[0]*len(record['candidates'])
        return _process(_new(work.parent),record,snap,apply=True)


def create(project,settings,content,width=1600):
    root=api.session_path(project);root.mkdir(parents=True,exist_ok=True)
    if manifest_paths(root):raise ValueError('Project already has a manifest')
    if not isinstance(settings,dict) or 'pages' in settings:raise ValueError('Settings contain version/size/theme/title, not page paths')
    record={'format':1,'project':str(root),'page':1,'width':width,'settings':settings,
            'baseToken':None,'operation':{'kind':'create'},'candidates':[content]}
    work=_new(_root(root))
    return _process(work,record,None,apply=True)
