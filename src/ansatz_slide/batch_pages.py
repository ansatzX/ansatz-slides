"""Resumable, idempotent multi-page publication with one manifest transaction."""
import copy
import json
from pathlib import Path
import re
import traceback
import uuid
from . import page_api as api
from .project import atomic_write, parse_document, manifest_paths, source_bytes
from .file_transactions import preserving_replace, retract_created
from .occupancy import require_pass


def _save(folder,name,value):
    atomic_write(folder/name,api.json_bytes(value),force=True)


def import_pages(project,plan,request_id,*,settings=None,after=None,allow_duplicates=False,width=1600):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):raise ValueError('request-id must be 1..80 letters, digits, _ or -')
    project=api.session_path(project)
    root=project if not project.is_file() else project.parent
    root.mkdir(parents=True,exist_ok=True)
    plan=Path(plan).resolve()
    document=parse_document(plan.read_text(),str(plan))
    if not isinstance(document,list) or not document or not all(isinstance(p,str) for p in document):
        raise ValueError('Plan must be a nonempty ordered list of page file paths, relative to the plan')
    candidates=[parse_document((plan.parent/p).read_text(),p) for p in document]
    digest=api.sha(api.json_bytes({'candidates':candidates,'settings':settings,'after':after,'allowDuplicates':allow_duplicates,'width':width}))
    folder=api.session_path(root/'.ansatz'/'batches'/request_id)
    with api.lock(root/'.ansatz-page-edit.lock'):
        if (folder/'request.json').exists():
            record=json.loads((folder/'request.json').read_text())
            if record['inputHash']!=digest:raise ValueError('request-id already used with different input; use the resume token for retained repairs or a new request-id')
        else:
            if not 400<=width<=8000:raise ValueError('Width must be 400..8000')
            existing=bool(manifest_paths(project))
            snap=api.snapshot(project) if existing else None
            if snap is not None and settings is not None:raise ValueError('Settings apply only to creation')
            if snap is None and (not isinstance(settings,dict) or 'pages' in settings):raise ValueError('New project requires settings without pages')
            count=len(snap['pages']) if snap else 0
            position=count if after is None else after
            if not 0<=position<=count:raise ValueError('--after must be 0..page count (0 inserts at start)')
            folder.mkdir(parents=True,exist_ok=True)
            paths=[]
            for i,candidate in enumerate(candidates,1):
                path=folder/f'candidate-{i}.page.yaml';atomic_write(path,api.json_bytes(candidate));paths.append(str(path))
            record={'inputHash':digest,'project':str(project),'root':str(root),'settings':settings,
                    'tracked':snap['tracked'] if snap else {},'existing':existing,'after':position,
                    'allowDuplicates':allow_duplicates,'width':width,'candidates':paths}
            _save(folder,'request.json',record)
    return resume(folder)


def resume(token):
    folder=api.session_path(token)
    record=json.loads((folder/'request.json').read_text())
    root=Path(record['root'])
    with api.lock(root/'.ansatz-page-edit.lock'):
        receipt=folder/'result.json'
        if receipt.exists():
            previous=json.loads(receipt.read_text())
            if previous.get('applied'):
                return {**previous,'replayed':True,'meaning':'Previously applied once; no new source writes. Receipt is historical, not a current deck audit.'}
        result={'format':'page-batch-v1','status':'blocked','applied':False,'resumeToken':str(folder),
                'candidateFiles':record['candidates'],'next':{'command':['ansatz-slide','deck','resume',str(folder)],
                'hint':'Repair retained candidate files, then resume. Source changes require a new plan/request after reviewing the current deck.'}}
        try:
            intent_path=folder/'publication.json'
            if intent_path.exists():
                intent=json.loads(intent_path.read_text());target=Path(intent['manifest'])
                if target.exists() and api.sha(target.read_bytes())==intent['hash'] and api.unchanged(intent['files']):
                    result.update(status='applied',applied=True,recovered=True,pages=intent['pages'])
                    result['next']['hint']='Batch was already published; resume only returns its receipt. Use a new request-id for further changes.'
                    _save(folder,'result.json',result);return result
                # An uncertain interrupted write must never insert a second batch.
                raise RuntimeError('Interrupted publication needs review; inspect publication.json and retained recovery files. No duplicate batch was inserted.')
            if record['existing']:
                if not api.unchanged(record['tracked']):raise RuntimeError('Source changed since batch preparation; inspect current deck and create a new request')
                snap=api.snapshot(record['project'])
            else:
                if manifest_paths(root):raise RuntimeError('Project appeared since preparation; use a new request after reviewing it')
                snap=None
            candidates=[parse_document(Path(p).read_text(),p) for p in record['candidates']]
            hashes=[api.page_fingerprint(c) for c in candidates]
            old_hashes={api.page_fingerprint(c) for c in snap['pages']} if snap else set()
            if not record['allowDuplicates'] and (len(set(hashes))!=len(hashes) or old_hashes.intersection(hashes)):
                raise ValueError('Duplicate page content detected; remove duplicates or submit a new request with --allow-duplicates for intentional repetition')
            settings=copy.deepcopy(snap['manifest'] if snap else record['settings'])
            fake={'root':root,'manifest':{**settings,'pages':[str(Path(p).relative_to(root)) for p in record['candidates']]},
                  'pages':candidates,'tracked':record['tracked']}
            from .validation import validate_project
            from .preflight import analyze, require_pass as require_sources, summary as source_summary
            validate_project(fake['manifest'], candidates, root, check_files=False)
            source_preflight = analyze(settings['size'], candidates, root, allow_remote=False, theme=settings.get('theme'))
            result['sourcePreflight'] = source_summary(source_preflight)
            require_sources(source_preflight)
            assets={};previews=[]
            attempt=folder/('attempt-'+uuid.uuid4().hex);attempt.mkdir()
            evidence_batch = api.preview_batch(fake, candidates, attempt, record['width'])
            for i,evidence in enumerate(evidence_batch,1):
                require_pass(evidence['geometry'])
                for path,digest in evidence['_assetHashes'].items():
                    if path in assets and assets[path]!=digest:raise RuntimeError('Assets changed between previews')
                    assets[path]=digest
                previews.append({'page':record['after']+i,'image':str(attempt/evidence['image'])})
            if not api.unchanged(record['tracked']) or not api.unchanged(assets):raise RuntimeError('Source or assets changed before publication')
            names=[f'page-{uuid.uuid4().hex}.page.yaml' for _ in candidates]
            current=list(settings.get('pages',[]));current[record['after']:record['after']]=names
            data=source_bytes(api.json_bytes({**settings,'pages':current}))
            target=snap['manifestPath'] if snap else root/'pptx.yaml'
            files={str(root/name):api.sha(source_bytes(api.json_bytes(c))) for name,c in zip(names,candidates)}
            intent={'manifest':str(target),'hash':api.sha(data),'files':files,'pages':previews}
            _save(folder,'publication.json',intent)
            for name,candidate in zip(names,candidates):atomic_write(root/name,source_bytes(api.json_bytes(candidate)))
            publication=None
            try:
                if not api.unchanged(record['tracked']) or not api.unchanged(assets):raise RuntimeError('Source or assets changed at publication')
                if snap:publication=preserving_replace(target,data,record['tracked'][str(target)])
                else:
                    if manifest_paths(root):raise RuntimeError('Project appeared at publication')
                    atomic_write(target,data)
                protected={p:h for p,h in record['tracked'].items() if p!=str(target)}
                if not api.unchanged(protected) or not api.unchanged(assets) or not api.unchanged(files):raise RuntimeError('Source/assets changed during publication')
                if api.sha(target.read_bytes())!=intent['hash']:raise RuntimeError('Manifest changed during publication')
            except Exception:
                if publication:publication.rollback()
                elif not snap:retract_created(target,intent['hash'])
                raise
            result.pop('checkingCandidate',None)
            result.update(status='applied',applied=True,pages=previews,pageCount=len(current))
            result['next']['hint']='Batch completed. Resume returns this receipt without inserting again; use a new request-id for further changes.'
        except Exception as exc:
            if hasattr(exc, 'candidate_number'):result['checkingCandidate']=exc.candidate_number
            if hasattr(exc,'report'):
                if exc.report.get('format') == 'source-preflight-v1':
                    from .preflight import summary as source_summary
                    result['sourcePreflight'] = source_summary(exc.report)
                else:
                    result['textFit']=exc.report
            diagnostic=folder/'execution-error.txt';diagnostic.write_text(traceback.format_exc())
            result.update(issues=[{'message':str(exc),'diagnostic':str(diagnostic)}])
        _save(folder,'result.json',result)
        return result
