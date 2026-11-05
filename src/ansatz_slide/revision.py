"""Checked sequential page revisions with staged final PPTX delivery.

Page publication remains per-page, not a whole-deck transaction. Any failure
reports already applied pages and leaves an existing delivery file untouched.
"""
from pathlib import Path
import json
import re
import time
import uuid

from . import page_api as api, work_objects as work
from .project import parse_document, export_project, atomic_write, source_bytes
from .rendering import render_pptx
from .output import compact_result
from .layout import apply_layout


def revise(project, plan_path, output, *, force=False, width=1600):
    started=time.perf_counter()
    if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
    snap=api.snapshot(project)
    plan_path=Path(plan_path).resolve()
    plan=parse_document(plan_path.read_text(encoding='utf-8'),str(plan_path))
    if isinstance(plan,dict):
        from .plan_revision import revise as revise_plan
        return revise_plan(project,plan_path,plan,output,force=force,width=width)
    if not isinstance(plan,list) or not plan:raise ValueError('Revision plan must be a nonempty list')
    output=Path(output).expanduser().resolve()
    protected=set(snap['tracked'])|{str(plan_path)}
    expected=dict(snap['tracked'])
    prepared=[];numbers=set()
    for item in plan:
        if not isinstance(item,dict) or set(item) not in ({'work','content'},{'work','edits'},{'work','layout'},{'work','edits','layout'}):
            raise ValueError('Each revision needs work and content, or edits and/or layout')
        ref=(plan_path.parent/Path(item['work'])).resolve()
        path,record=work._read(ref)
        current=work._current(path,record)
        if current is None or record['operation']['kind']!='edit':raise ValueError('Revision requires existing-page edit work')
        if current['manifestPath']!=snap['manifestPath']:raise ValueError('Work belongs to another project')
        number=record['page']
        if number in numbers:raise ValueError('Duplicate page in revision plan')
        numbers.add(number)
        candidate=record['candidates'][0]
        if 'content' in item:
            content=(plan_path.parent/Path(item['content'])).resolve();protected.add(str(content))
            candidate=parse_document(content.read_text(encoding='utf-8'),str(content))
        elif 'edits' in item:
            edits=item['edits']
            if not isinstance(edits,list) or not edits:raise ValueError('Edits must be a nonempty list')
            for edit in edits:
                if not isinstance(edit,dict) or set(edit)!={'element','changes'}:raise ValueError('Invalid element edit')
                candidate=api.patch_element(candidate,edit['element'],edit['changes'])
        if 'layout' in item:candidate=apply_layout(candidate,item['layout'])
        # Snapshot dependencies introduced by any candidate before publishing pages.
        for image in api.image_objects(candidate):
            if not re.match(r'(?i)^(data:|https?://)', image['src']):
                asset = api.safe_path(snap['root'], image['src'], 'image')
                name = str(asset); digest = api.sha(asset.read_bytes())
                if name in expected and expected[name] != digest:
                    raise RuntimeError('Asset changed during revision preflight')
                expected[name] = digest; protected.add(name)
        prepared.append((path,number,candidate))
    if str(output) in protected:raise ValueError('Output must not overwrite source, assets, plan or candidates')
    if output.exists() and not force:raise FileExistsError('Output exists; use --force')
    original_output=api.sha(output.read_bytes()) if output.exists() else None
    folder=api.session_path(snap['root']/'.ansatz'/'deliveries'/uuid.uuid4().hex)
    folder.mkdir(parents=True)
    result={'format':'deck-revision-v1','status':'blocked','appliedPages':[],
            'exported':False,'output':str(output),'pages':[],'issues':[],
            'timings':[],'report':str(folder/'result.json'),
            'publication':'Per-page source writes; final PPTX published only after all edits and final render pass.'}
    def timed(label,callback):
        tick=time.perf_counter()
        try:return callback()
        finally:result['timings'].append({'stage':label,'seconds':round(time.perf_counter()-tick,4)})
    try:
        for ref,number,candidate in prepared:
            if not api.unchanged(expected):raise RuntimeError('Source changed during revision; reopen remaining work')
            candidate_file=folder/f'candidate-{number}.page.yaml'
            candidate_file.write_bytes(api.json_bytes(candidate))
            page=timed(f'update-page-{number}',lambda:work.update(ref,content=candidate_file))
            result['pages'].append(compact_result(page))
            if page.get('applied'):
                result['appliedPages'].append(number)
                expected[str(snap['paths'][number-1])]=api.sha(source_bytes(api.json_bytes(candidate)))
            if page.get('status')!='applied' or page.get('issues'):
                result['issues'].append({'page':number,'message':'Page rejected; use returned work to repair. Remaining edits and export were not run.'})
                break
        else:
            if not api.unchanged(expected):raise RuntimeError('Source changed before export')
            candidate_pptx=folder/'candidate.pptx'
            result['export']=timed('export',lambda:export_project(project,candidate_pptx,transition='none',allow_remote=False,measure_text=True))
            renderer=timed('render-final',lambda:render_pptx(candidate_pptx,folder,width))
            images=sorted(folder.glob('page-*.png'),key=lambda p:int(p.stem.rsplit('-',1)[1]))
            if len(images)!=len(snap['pages']) or any(not p.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for p in images):
                raise RuntimeError('Final renderer returned incomplete PNG pages')
            if not api.unchanged(expected):raise RuntimeError('Source changed while rendering; final output not published')
            current_output=api.sha(output.read_bytes()) if output.exists() else None
            if current_output!=original_output:raise RuntimeError('Delivery file changed concurrently; refusing replacement')
            atomic_write(output,candidate_pptx.read_bytes(),force=force)
            result.update(status='applied',exported=True,
                          preview={'renderer':{**renderer,'scope':'Final exported PPTX, static render; native PowerPoint/WPS unverified'},
                                   'images':[str(p) for p in images],
                                   'changedPageImages':[str(images[n-1]) for n in sorted(numbers)],
                                   'visualReview':'not performed; open changedPageImages before delivery'})
            result['export']['output']=str(output)
            from .review import write as write_review
            final_snap=api.snapshot(project)
            result['review']=write_review(folder,final_snap,final_snap['pages'],images,[],
                                          changed=numbers,pptx=output,delivered=True)
    except Exception as exc:
        result['issues'].append({'kind':type(exc).__name__,'message':str(exc)})
    result['elapsedSeconds']=round(time.perf_counter()-started,4)
    atomic_write(folder/'result.json',api.json_bytes(result))
    return result
