"""Revision-bound page work objects: candidate, evidence and one next operation."""
import copy
import json
from pathlib import Path
import uuid
import traceback

from . import page_api as api
from . import outline
from .occupancy import write_geometry, check_geometry, require_pass
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
    result={'format':'page-work-v1','work':str(work),'resumeToken':str(work.parent),**result}
    attach_gates(result)
    result['next']={'command':['ansatz-slide','page','update',str(work)],
                    'hint':'Modify a candidate with --element ID --changes FILE or --content FILE; no arguments retries the retained candidate.'}
    result['repair']={'candidateFiles':[i['editable'] for i in result.get('candidates',[])],
        'rules':'Geometry failure: bounds/rotation/order only, or content-preserving split. Text/table overflow: use measured required dimensions, then check geometry again. No content is silently removed.',
        'recoveryCommand':['ansatz-slide','page','resume',str(work.parent)]}
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
            'next':{'command':['ansatz-slide','page','rebase',str(work.parent)],
                    'hint':'Rebase resolves the latest candidate against its source path, not the old page number. If the source was removed, explicitly supply --page. Review the rebased candidate before update; no automatic overwrite.'}}))


def _current(work,record):
    head=json.loads((work.parent/'head.json').read_text())
    if head['work']!=str(work):raise ValueError('This work reference was superseded; use the work returned by the last operation')
    if record['operation']['kind']=='create':
        if manifest_paths(record['project']):raise ValueError('Project was already created')
        return None
    snap=api.snapshot(record['project'])
    if not 1<=record['page']<=len(snap['pages']):raise ValueError('Original page index no longer exists; rebase the retained work')
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
            geometry=write_geometry(size,candidate,work/f'geometry-{i}')
            item['geometry']=geometry
        except Exception as exc:
            issues.append({'candidate':i,'kind':'geometry-input','message':str(exc)})
        try:
            manifest={**(record['settings'] if snap is None else snap['manifest']),'pages':[str(path.relative_to(root))]}
            validate_project(manifest,[candidate],root)
            from .preflight import analyze, require_pass as require_sources, summary as source_summary
            source_preflight = analyze(size, [candidate], root, allow_remote=False, theme=manifest.get('theme'))
            item['sourcePreflight'] = source_summary(source_preflight)
            require_sources(source_preflight)
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
                                position=operation.get('position','after'),allow_duplicates=operation.get('allowDuplicates',False),anchor_session=other_session,anchor_token=other_token)
    raise ValueError('Unknown work operation')


def _process(work,record,snap,*,apply,render=True):
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
                record.update(project=str(project),page=number,sourcePath=str(updated['paths'][number-1]),baseToken=api.page_token(updated,number),
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
            elif render:
                rendered=api.preview(snap,record['page'],record['candidates'][0],work,record['width'])
                result['textFit']=[rendered['typography']]
                items[0]['preview']={'image':str(work/rendered['image']) if rendered['image'] else None,
                                     'pptx':str(work/rendered['previewPptx']) if rendered['previewPptx'] else None}
        except Exception as exc:
            if hasattr(exc,'report'):result['textFit']=[exc.report]
            if not result['applied']:
                result['status']='conflict' if 'concurrent' in str(exc).lower() or 'changed' in str(exc).lower() or 'stale' in str(exc).lower() else 'blocked'
            diagnostic=work/'execution-error.txt'
            diagnostic.write_text(traceback.format_exc(),encoding='utf-8')
            result['issues'].append({'kind':'execution','message':str(exc),'diagnostic':str(diagnostic)})
            if not result['applied'] and snap is not None and 'Geometry precheck failed' in str(exc):
                result['blockingPages']=[]
                for number,page in enumerate(snap['pages'],1):
                    report=check_geometry(snap['manifest']['size'],page)
                    if report['status']=='blocked':
                        report=write_geometry(snap['manifest']['size'],page,work/f'blocking-page-{number}')
                        result['blockingPages'].append({'page':number,'source':str(snap['paths'][number-1]),'geometry':report})
    if not apply and not render:
        result['previewStatus']='not_requested'
        result['textFit']=[{'status':'unverified','reason':'Read-only open skipped rendering; update still requires text measurement and preview.'}]
    return _finish(work,record,result)


def open_page(project,number,width=1600,*,render=True):
    if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
    snap=api.snapshot(project)
    if not 1<=number<=len(snap['pages']):raise ValueError('Page out of range')
    root=_root(snap['root']);work=_new(root)
    record={'format':1,'project':str(snap['manifestPath']),'page':number,'width':width,
            'sourcePath':str(snap['paths'][number-1]),'baseToken':api.page_token(snap,number),'operation':{'kind':'edit'},
            'candidates':[snap['pages'][number-1]]}
    return _process(work,record,snap,apply=False,render=render)


def update(work,content=None,element=None,changes=None,candidate=1,*,edits=None,layout=None,allow_duplicates=False):
    work,record=_read(work)
    with api.lock(work.parent/'.work.lock'):
        try:snap=_current(work,record)
        except Exception as exc:return _conflict(work,record,str(exc))
        record=copy.deepcopy(record)
        if allow_duplicates:
            if record['operation']['kind']!='insert':raise ValueError('--allow-duplicates only applies to a retained insertion')
            record['operation']['allowDuplicates']=True
        if not 1<=candidate<=len(record['candidates']):raise ValueError('Candidate index out of range')
        if sum(value is not None for value in (content,element,edits))>1:raise ValueError('Choose full content, one element update, or edits')
        if layout is not None and (content is not None or element is not None):raise ValueError('Layout can be combined with edits, not content or element')
        original=record['candidates'][candidate-1]
        if content is not None:record['candidates'][candidate-1]=parse_document(Path(content).read_text(),str(content))
        elif element is not None:
            record['candidates'][candidate-1]=api.patch_element(record['candidates'][candidate-1],element,changes)
        if edits is not None:
            if not isinstance(edits,list) or not edits:raise ValueError('Edits must be a nonempty list of {element, changes}')
            for edit in edits:
                if not isinstance(edit,dict) or set(edit)!={'element','changes'} or not isinstance(edit['element'],str) or not isinstance(edit['changes'],dict):
                    raise ValueError('Each edit needs exactly element (string) and changes (object)')
                record['candidates'][candidate-1]=api.patch_element(record['candidates'][candidate-1],edit['element'],edit['changes'])
        if layout is not None:
            from .layout import apply_layout
            record['candidates'][candidate-1]=apply_layout(record['candidates'][candidate-1],layout)
        failures=record.get('geometryFailures',[])
        if candidate<=len(failures) and failures[candidate-1]>0:
            if _content_signature(original)!=_content_signature(record['candidates'][candidate-1]):
                return _layout_rejection(work,'After geometry failure, only bounds/rotation and element ordering may change. Content, styles and elements are frozen; rejected input did not replace the retained candidate.')
        return _process(_new(work.parent),record,snap,apply=True)


def change(work,kind,contents=(),other=None,position='after',*,allow_duplicates=False):
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
        record['operation']={'kind':'create' if creating else kind,'position':position,'other':str(other) if other else None,'allowDuplicates':allow_duplicates}
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


def resume(token):
    """Resolve a stable lineage token without applying or rebasing a candidate."""
    token=api.session_path(token)
    root=token if (token/'head.json').is_file() else token.parent
    work=api.session_path(json.loads((root/'head.json').read_text())['work'])
    if work.parent!=root:raise ValueError('Invalid work head')
    work,record=_read(work)
    try:_current(work,record)
    except Exception as exc:return _conflict(work,record,str(exc))
    return json.loads((work/'result.json').read_text())


def rebase(token,number=None):
    """Explicitly recover candidates after source changes; never publish here."""
    current=resume(token);work,record=_read(current['work'])
    with api.lock(work.parent/'.work.lock'):
        if json.loads((work.parent/'head.json').read_text())['work']!=str(work):
            raise ValueError('Work changed during rebase; retry resume')
        if record['operation']['kind']=='create':raise ValueError('Creation cannot be rebound onto an existing project')
        snap=api.snapshot(record['project'])
        if number is None:
            matches=[i+1 for i,p in enumerate(snap['paths']) if str(p)==record.get('sourcePath')]
            if len(matches)!=1:raise ValueError('Source anchor removed or unavailable; inspect deck outline and explicitly choose --page N')
            number=matches[0]
        if not 1<=number<=len(snap['pages']):raise ValueError('Rebase page out of range')
        if record['operation']['kind'] in ('move','merge'):
            raise ValueError('Reopen both current pages before merge/move; ambiguous second anchor is not rebound automatically')
        record=copy.deepcopy(record)
        previous=json.loads((work/'result.json').read_text())
        if previous.get('applied') or (previous.get('status')=='ready' and not record.get('rebasedPending')):
            record['candidates']=[copy.deepcopy(snap['pages'][number-1])]
        record['rebasedPending']=not previous.get('applied') and (previous.get('status')!='ready' or record.get('rebasedPending',False))
        record.update(page=number,sourcePath=str(snap['paths'][number-1]),baseToken=api.page_token(snap,number))
        result=_process(_new(work.parent),record,snap,apply=False,render=False)
        result['rebaseReviewRequired']=True
        result['next']['hint']='Inspect current context and retained candidate before update. Rebase has not published any source changes.'
        atomic_write(Path(result['work'])/'result.json',api.json_bytes(result),force=True)
        return result
