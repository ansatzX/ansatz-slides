"""Project-level plans: one snapshot, batched checks, one final render.

Sources are only published after the complete candidate has passed checks and
rendered. Files use retained replacement/rollback; no crash-atomic multi-file
transaction is claimed.
"""
import copy
import json
from pathlib import Path
import re
import time
import uuid

from . import page_api as api, work_objects as work, review, outline, narrative
from .project import atomic_write, parse_document, source_bytes, validate_project
from .layout import apply_layout
from .occupancy import write_geometry
from .typography import check_pages
from .rendering import render_pptx
from .file_transactions import preserving_replace, retract_created


def contexts(snap,numbers):
    return [{'page':n,**{k:v for k,v in outline.context(snap,n).items() if k!='narrative'}} for n in numbers]


def open_deck(project, numbers=None, *, width=1600, render=True):
    if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
    snap=api.snapshot(project)
    numbers=numbers or list(range(1,len(snap['pages'])+1))
    if not numbers or len(set(numbers))!=len(numbers) or any(n<1 or n>len(snap['pages']) for n in numbers):
        raise ValueError('Select distinct existing pages')
    folder=api.session_path(snap['root']/'.ansatz'/'revisions'/uuid.uuid4().hex);folder.mkdir(parents=True)
    record={'format':'deck-plan-base-v1','project':str(snap['manifestPath']),
            'tracked':snap['tracked'],'selected':numbers,'width':width,'frozen':{}}
    atomic_write(folder/'snapshot.json',api.json_bytes(record))
    plan={'base':str(folder/'snapshot.json'),'pages':[{'page':n,'edits':[]} for n in numbers]}
    atomic_write(folder/'plan.yaml',api.json_bytes(plan))
    result={'status':'ready','base':str(folder/'snapshot.json'),'plan':str(folder/'plan.yaml'),
            'pages':[{'page':n,'source':str(snap['paths'][n-1]),'content':snap['pages'][n-1],
                      'context':{k:v for k,v in outline.context(snap,n).items() if k!='narrative'}} for n in numbers]}
    result['narrative']=narrative.view(snap)
    if render:
        try:
            evidence=api.preview_batch(snap,[snap['pages'][n-1] for n in numbers],folder,width)
            for row,e in zip(result['pages'],evidence):row['image']=str(folder/e['image'])
        except Exception as exc:
            result.update(status='blocked',issues=[{'kind':type(exc).__name__,'message':str(exc)}],
                          next={'hint':'Edit the retained plan, then use deck revise; no source writes occurred.'})
    return result


def _prepare(snap, record, document, plan_path):
    entries=document.get('pages')
    if set(document)!={'base','pages'} or not isinstance(entries,list) or not entries:raise ValueError('Plan needs base and a nonempty pages list')
    candidates=copy.deepcopy(snap['pages']);numbers=set();protected=set(snap['tracked'])|{str(plan_path)}
    expected=dict(snap['tracked'])
    for item in entries:
        if not isinstance(item,dict) or 'page' not in item:raise ValueError('Each plan entry needs page')
        ops=set(item)-{'page'}
        if ops not in ({'content'},{'edits'},{'layout'},{'edits','layout'}):raise ValueError('Page entry needs content, edits and/or layout')
        n=item['page']
        if type(n) is not int or n not in record['selected']:raise ValueError('Plan page was not selected in this snapshot')
        if n in numbers:raise ValueError('Duplicate page in plan')
        numbers.add(n);candidate=candidates[n-1]
        if 'content' in item:
            path=(plan_path.parent/item['content']).resolve();protected.add(str(path))
            candidate=parse_document(path.read_text(),str(path))
        if 'edits' in item:
            if not isinstance(item['edits'],list):raise ValueError('Edits must be a list')
            for edit in item['edits']:
                if not isinstance(edit,dict) or set(edit)!={'element','changes'}:raise ValueError('Invalid element edit')
                candidate=api.patch_element(candidate,edit['element'],edit['changes'])
        if 'layout' in item:candidate=apply_layout(candidate,item['layout'])
        frozen=record.get('frozen',{}).get(str(n))
        if frozen and work._content_signature(candidate)!=work._content_signature(frozen):
            raise ValueError(f'Page {n}: after geometry failure only bounds/rotation/order may change; retained content must be preserved')
        candidates[n-1]=candidate
    validate_project(snap['manifest'],candidates,snap['root'])
    for image in api.image_objects({'pages':candidates}):
        if not re.match(r'(?i)^(data:|https?://)',image['src']):
            path=api.safe_path(snap['root'],image['src'],'image');name=str(path);digest=api.sha(path.read_bytes())
            if name in expected and expected[name]!=digest:raise RuntimeError('Asset changed during preflight')
            expected[name]=digest;protected.add(name)
    return candidates,numbers,expected,protected


def revise(project, plan_path, document, output, *, force=False, width=1600):
    started=time.perf_counter();plan_path=Path(plan_path).resolve()
    if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
    snap=api.snapshot(project)
    base=(plan_path.parent/document['base']).resolve()
    if base.name!='snapshot.json' or base.parent.parent!=snap['root']/'.ansatz'/'revisions':raise ValueError('Base must be a deck open snapshot in this project')
    folder=base.parent;digest=api.sha(api.json_bytes(document));output=Path(output).resolve()
    with api.lock(snap['root']/'.ansatz-page-edit.lock'):
        record=json.loads(base.read_text())
        if record.get('format')!='deck-plan-base-v1' or record['project']!=str(snap['manifestPath']):raise ValueError('Snapshot belongs to another project')
        if record.get('applied'):
            if digest!=record['planHash'] or str(output)!=record['output']:raise ValueError('Plan already applied; use deck open for a new edit')
            if not api.unchanged(record['tracked']) or not output.exists() or api.sha(output.read_bytes())!=record['outputHash']:raise ValueError('Applied plan or delivery changed; reopen the project')
            return {**json.loads((folder/'result.json').read_text()),'replayed':True}
        if not api.unchanged(record['tracked']):raise ValueError('Source changed since deck open; reopen the project before revising')
        if (folder/'publication.json').exists():raise RuntimeError('Interrupted publication: inspect retained publication.json and recovery files before retrying')
        candidates,numbers,expected,protected=_prepare(snap,record,document,plan_path)
        protected.add(str(base))
        if str(output) in protected or output.is_relative_to(snap['root']/'.ansatz') or output.is_relative_to(snap['root']/'.ansatz-recovery'):
            raise ValueError('Output must not overwrite source, assets, plan or internal state')
        if output.exists() and not force:raise FileExistsError('Output exists; use --force')
        old_output=api.sha(output.read_bytes()) if output.exists() else None
        attempt=folder/('attempt-'+uuid.uuid4().hex);attempt.mkdir()
        result={'format':'deck-revision-v2','status':'blocked','appliedPages':[],'exported':False,
                'output':str(output),'plan':str(plan_path),'base':str(base),'issues':[],
                'context':contexts(snap,sorted(numbers)),'narrative':narrative.view(snap),
                'timings':[],'report':str(attempt/'result.json')}
        checks={};issues=result['issues'];images=[];candidate_pptx=None;publications=[];output_publication=None;created_output=False
        def timed(stage,fn):
            t=time.perf_counter()
            try:return fn()
            finally:result['timings'].append({'stage':stage,'seconds':round(time.perf_counter()-t,4)})
        try:
            for n,page in enumerate(candidates,1):
                atomic_write(attempt/f'candidate-{n}.page.yaml',api.json_bytes(page))
                g=write_geometry(snap['manifest']['size'],page,attempt/f'geometry-{n}')
                checks[n]={'geometry':g['status'],'text':'not_run'}
                if g['status']!='passed':
                    record['frozen'][str(n)]=page
                    common={'page':n,'kind':'geometry','evidence':str(attempt/f'geometry-{n}'/'report.json'),
                            'candidate':str(attempt/f'candidate-{n}.page.yaml')}
                    for item in g['outOfBounds']:
                        issues.append({**common,'element':item['elementId'],'bounds':item['bounds'],
                                       'message':'Element extends beyond the canvas; reposition or resize its bounds.'})
                    for item in g['unapprovedOverlaps']:
                        issues.append({**common,'element':' / '.join(item['elements']),
                                       'message':'Undeclared element overlap; adjust the retained layout.', 'intersection':item.get('intersection')})
                    for ident in g['invalidDegenerateBounds']:
                        issues.append({**common,'element':ident,'message':'Element has invalid zero-area bounds.'})
            atomic_write(base,api.json_bytes(record),force=True)
            if not issues:
                from .preflight import analyze, require_pass as require_sources, summary as source_summary
                source_preflight = analyze(snap['manifest']['size'], candidates, snap['root'], allow_remote=False,
                                           include_geometry=False, theme=snap['manifest'].get('theme'))
                result['sourcePreflight'] = source_summary(source_preflight)
                require_sources(source_preflight)
                reports=timed('measure-batch',lambda:check_pages(snap['manifest']['size'],candidates,snap['manifest'].get('theme',{}),attempt/'text-fit'))
                for n,r in enumerate(reports,1):
                    checks[n]['text']=r['status']
                    for item in r['elements']:
                        if item['status']!='passed':issues.append({'page':n,'element':item['elementId'],'kind':'text',
                            'message':item.get('reason',item['status']),'repair':item.get('repair'),
                            'evidence':str(attempt/'text-fit'/str(n)/'text-fit.json')})
                selected={**copy.deepcopy(snap['manifest']),'pages':copy.deepcopy(candidates)}
                candidate_pptx=attempt/'candidate.pptx'
                def export():
                    data=api.export_pptx(selected,{'images':api.resolve_images(selected,snap['root'],allow_remote=False),
                                                 'slideTransition':{'effect':'none','speed':'fast'}})
                    if api.inspect_pptx(data)['pageCount']!=len(candidates):raise RuntimeError('Export page count mismatch')
                    atomic_write(candidate_pptx,data)
                timed('export',export)
                render_folder=attempt/'review'/'pages';render_folder.mkdir(parents=True)
                renderer=timed('render-final',lambda:render_pptx(candidate_pptx,render_folder,width))
                images=sorted(render_folder.glob('page-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
                if len(images)!=len(candidates) or any(not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for p in images):raise RuntimeError('Final renderer returned incomplete PNG pages')
                result['preview']={'renderer':renderer,'images':[str(p) for p in images],
                                   'changedPageImages':[str(images[n-1]) for n in sorted(numbers)],'visualReview':'not performed'}
            if not issues:
                if not api.unchanged(expected):raise RuntimeError('Source/assets changed during checks; no source writes')
                current_output=api.sha(output.read_bytes()) if output.exists() else None
                if current_output!=old_output:raise RuntimeError('Delivery changed during checks')
                writes={str(snap['paths'][n-1]):source_bytes(api.json_bytes(candidates[n-1])) for n in numbers
                        if candidates[n-1]!=snap['pages'][n-1]}
                intent={'files':{p:api.sha(data) for p,data in writes.items()},'output':str(output),
                        'outputHash':api.sha(candidate_pptx.read_bytes()),'original':expected}
                atomic_write(folder/'publication.json',api.json_bytes(intent))
                for path,data in writes.items():
                    if not api.unchanged(expected):raise RuntimeError('Concurrent source change at publication')
                    publications.append(preserving_replace(Path(path),data,expected[path]));expected[path]=api.sha(data)
                if not api.unchanged(expected):raise RuntimeError('Concurrent source change after publication')
                if old_output is not None:output_publication=preserving_replace(output,candidate_pptx.read_bytes(),old_output)
                else:atomic_write(output,candidate_pptx.read_bytes());created_output=True
                if not api.unchanged(expected):raise RuntimeError('Concurrent source change during delivery')
                result.update(status='applied',exported=True,appliedPages=sorted(n for n in numbers if str(snap['paths'][n-1]) in writes))
                record.update(applied=True,planHash=digest,output=str(output),outputHash=intent['outputHash'],tracked=expected)
        except Exception as exc:
            if output_publication:output_publication.rollback()
            elif created_output:retract_created(output,api.sha(candidate_pptx.read_bytes()))
            for publication in reversed(publications):publication.rollback()
            if publications or output_publication or created_output:
                # A completed rollback is retryable only if all original files are back.
                if api.unchanged(snap['tracked']):(folder/'publication.json').unlink(missing_ok=True)
            issues.append({'kind':type(exc).__name__,'message':str(exc)})
        final_snap={**snap,'pages':candidates,'tracked':expected} if result['exported'] else snap
        result['context']=contexts(final_snap,sorted(numbers))
        result['narrative']=narrative.view(final_snap)
        result['review']=review.write(attempt/'review',{**snap,'tracked':expected if result['exported'] else snap['tracked']},candidates,images,issues,
                                     changed=numbers,checks=checks,pptx=output if result['exported'] else candidate_pptx,
                                     delivered=result['exported'])
        result['elapsedSeconds']=round(time.perf_counter()-started,4)
        atomic_write(attempt/'result.json',api.json_bytes(result))
        atomic_write(folder/'result.json',api.json_bytes(result),force=True)
        atomic_write(base,api.json_bytes(record),force=True)
        return result
