"""Focus edits on one page, with explicit local split and adjacent merge operations."""
import copy
from contextlib import contextmanager
import hashlib
import html
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid

from . import export_pptx
from .inspection import inspect_pptx
from .project import find_manifest, parse_document, image_objects, resolve_images, atomic_write, source_bytes
from .file_transactions import preserving_replace
from .rendering import render_pptx
from .typography import check_page as measure_text, check_pages as measure_pages, require_pass as require_text
from .validation import validate_project, safe_path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def page_fingerprint(page):
    """Structural page identity independent of JSON/YAML mapping key order."""
    return sha(json.dumps(page,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')


def session_path(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Session path must not contain symlinks')
    if path.exists():
        if not path.is_dir(): raise ValueError('Session must be a directory')
        for base, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                item = Path(base)/name
                mode = item.lstat().st_mode
                if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise ValueError(f'Session artifacts must not be symlinks or special files: {item}')
    return path


def session_write(session, name, data):
    session_path(session)
    # Bind writes to the opened directory; replace the final name, never resolve
    # it through a symlink. Only fixed immediate-child artifact names are allowed.
    if name not in ('page.page.yaml', 'session.json'):
        raise ValueError('Unknown session artifact')
    fd = os.open(session, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    temporary = '.write-' + uuid.uuid4().hex
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd)
        with os.fdopen(out, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        try: os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError: pass
        os.close(fd)


@contextmanager
def lock(path):
    """Kernel-owned lock; keep the inode stable so process death releases ownership."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Lock must be a regular file')
        if os.name == 'nt':
            import msvcrt
            if os.fstat(fd).st_size == 0: os.write(fd, b'0')
            os.lseek(fd, 0, os.SEEK_SET)
            try: msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc: raise RuntimeError(f'Another edit/check owns {path}; retry after it finishes') from exc
        else:
            import fcntl
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc: raise RuntimeError(f'Another edit/check owns {path}; retry after it finishes') from exc
        yield
    finally:
        # Do not unlink: waiters and new arrivals must lock the same inode.
        os.close(fd)


def snapshot(project):
    manifest_path = find_manifest(project)
    root = manifest_path.parent
    manifest_data = manifest_path.read_bytes()
    manifest = parse_document(manifest_data.decode('utf-8'), str(manifest_path))
    pages, paths = [], []
    tracked = {str(manifest_path): sha(manifest_data)}
    for rel in manifest.get('pages', []):
        path = safe_path(root, rel, 'page')
        if not path.name.lower().endswith('.page.yaml'):
            raise ValueError('Page source must use .page.yaml')
        if path in paths:
            raise ValueError('Single-page editing requires distinct page source paths; this manifest reuses a page file')
        paths.append(path)
        data = path.read_bytes(); tracked[str(path)] = sha(data)
        pages.append(parse_document(data.decode('utf-8'), str(path)))
    validate_project(manifest, pages, root)
    for image in image_objects({'manifest': manifest, 'pages': pages}):
        src = image['src']
        if not re.match(r'(?i)^(data:|https?://)', src):
            path = safe_path(root, src, 'image'); tracked[str(path)] = sha(path.read_bytes())
    return {'manifestPath': manifest_path, 'root': root, 'manifest': manifest,
            'pages': pages, 'paths': paths, 'tracked': tracked}


def unchanged(tracked):
    return all(Path(p).is_file() and sha(Path(p).read_bytes()) == value for p, value in tracked.items())


def page_token(snap, number):
    path = snap['paths'][number-1]
    tracked = {str(snap['manifestPath']): snap['tracked'][str(snap['manifestPath'])],
               str(path): snap['tracked'][str(path)]}
    for image in image_objects({'manifest': snap['manifest'], 'page': snap['pages'][number-1]}):
        if not re.match(r'(?i)^(data:|https?://)', image['src']):
            p = safe_path(snap['root'], image['src'], 'image')
            tracked[str(p)] = snap['tracked'][str(p)]
    return sha(json_bytes([number, tracked]))


def presentation_token(snap, number):
    page = snap['pages'][number-1]
    tracked = {str(snap['paths'][number-1]): snap['tracked'][str(snap['paths'][number-1])]}
    for image in image_objects({'manifest':snap['manifest'], 'page':page}):
        if not re.match(r'(?i)^(data:|https?://)', image['src']):
            path = safe_path(snap['root'], image['src'], 'image')
            tracked[str(path)] = snap['tracked'][str(path)]
    appearance = {key:snap['manifest'].get(key) for key in ('size','theme','customFonts')}
    return sha(json_bytes([tracked, appearance]))


def title(page):
    candidates = []
    for element in page.get('elements', []):
        content = element.get('content', {})
        if element.get('elementType') == 'text' and isinstance(content, dict):
            text = html.unescape(re.sub('<[^>]*>', '', content.get('text', ''))).strip()
            if text:
                priority = 10000 if element.get('elementId', '').lower() in ('title','heading') else 0
                candidates.append((priority + content.get('fontSize', 0), text))
    return max(candidates, default=(0, ''), key=lambda v: v[0])[1]


def context(snap, number):
    return [{'page': i+1, 'title': title(p)} for i, p in enumerate(snap['pages'])
            if abs(i+1-number) == 1]


def preview(snap, number, candidate, session, width):
    if not isinstance(candidate, dict) or 'pages' in candidate:
        raise ValueError('Edit input must be exactly one page object, not a deck or page list')
    pages = copy.deepcopy(snap['pages']); pages[number-1] = candidate
    validate_project(snap['manifest'], pages, snap['root'])
    selected = {**copy.deepcopy(snap['manifest']), 'pages': [copy.deepcopy(candidate)]}
    assets = {}
    for image in image_objects(selected):
        if not re.match(r'(?i)^(data:|https?://)', image['src']):
            p = safe_path(snap['root'], image['src'], 'image'); assets[str(p)] = sha(p.read_bytes())
    versions = session/'versions'; versions.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preview-', dir=versions) as scratch:
        stage = Path(scratch).resolve()
        from .occupancy import write_geometry
        geometry = write_geometry(snap['manifest']['size'], candidate, stage/'geometry')
        image_name = None
        typography = None
        renderer = {'name':None, 'reason':'Geometry precheck blocked; no PPTX or Office render created'}
        if geometry['status']=='passed':
            typography = measure_text(snap['manifest']['size'],candidate,snap['manifest'].get('theme',{}),session/('text-fit-'+uuid.uuid4().hex))
            typography['page']=number
            require_text(typography)
            data = export_pptx(selected, {'images': resolve_images(selected, snap['root'], allow_remote=False),
                                      'slideTransition': {'effect':'none','speed':'fast'}})
            if inspect_pptx(data)['pageCount'] != 1:
                raise RuntimeError('Preview must contain exactly one page')
            (stage/'page.pptx').write_bytes(data)
            renderer = render_pptx(stage/'page.pptx', stage, width)
            images = list(stage.glob('page-*.png'))
            if len(images) != 1 or not images[0].read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('Renderer must produce exactly one PNG')
            image_name = images[0].name
        if not unchanged(snap['tracked']) or not unchanged(assets):
            raise RuntimeError('Source or assets changed during preview; retry page check')
        target = versions/uuid.uuid4().hex
        geometry['files'] = {k:str(target/'geometry'/Path(v).name) for k,v in geometry['files'].items()}
        (stage/'geometry'/'report.json').write_bytes(json_bytes(geometry))
        stage.rename(target)
    return {'image': str((target/image_name).relative_to(session)) if image_name else None,
            'previewPptx': str((target/'page.pptx').relative_to(session)) if image_name else None,
            'renderer': renderer, 'geometry':geometry, 'typography':typography, '_assetHashes':assets}


def preview_batch(snap, candidates, session, width):
    """Check a candidate batch and render bounded groups, without publishing it."""
    from .occupancy import write_geometry, require_pass
    validate_project(snap['manifest'], candidates, snap['root'])
    selected = {**copy.deepcopy(snap['manifest']), 'pages': copy.deepcopy(candidates)}
    assets = {}
    for image in image_objects(selected):
        if not re.match(r'(?i)^(data:|https?://)', image['src']):
            path = safe_path(snap['root'], image['src'], 'image')
            assets[str(path)] = sha(path.read_bytes())
    geometries = []
    for number, candidate in enumerate(candidates, 1):
        geometry = write_geometry(snap['manifest']['size'], candidate,
                                  session / f'geometry-{number}')
        try:
            require_pass(geometry, label=f'candidate {number}')
        except Exception as exc:
            exc.candidate_number = number
            raise
        geometries.append(geometry)
    reports = measure_pages(snap['manifest']['size'], candidates,
                            snap['manifest'].get('theme', {}), session / 'text-fit')
    for report in reports:
        try:
            require_text(report)
        except Exception as exc:
            exc.candidate_number = report['page']
            raise
    evidence = []
    for start in range(0, len(candidates), 16):
        group = candidates[start:start + 16]
        stage = session / f'render-{start + 1}'
        stage.mkdir()
        rendered = {**selected, 'pages': copy.deepcopy(group)}
        data = export_pptx(rendered, {'images': resolve_images(rendered, snap['root'], allow_remote=False),
                                     'slideTransition': {'effect': 'none', 'speed': 'fast'}})
        if inspect_pptx(data)['pageCount'] != len(group):
            raise RuntimeError('Batch preview page count mismatch')
        (stage / 'pages.pptx').write_bytes(data)
        renderer = render_pptx(stage / 'pages.pptx', stage, width)
        images = sorted(stage.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
        if len(images) != len(group) or any(not image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for image in images):
            raise RuntimeError('Batch renderer must produce one PNG per candidate')
        for offset, image in enumerate(images):
            index = start + offset
            evidence.append({'image': str(image.relative_to(session)),
                             'previewPptx': str((stage / 'pages.pptx').relative_to(session)),
                             'renderer': renderer, 'geometry': geometries[index],
                             'typography': reports[index], '_assetHashes': assets})
    if not unchanged(snap['tracked']) or not unchanged(assets):
        raise RuntimeError('Source or assets changed during batch preview; retry')
    return evidence


def response(session, state, snap):
    number = state['page']
    return {'session': str(session), 'page': number, 'pageCount': len(snap['pages']),
            'token': state['token'], 'sourcePage': str(snap['paths'][number-1]),
            'editablePage': str(session/'page.page.yaml'), 'pageSource': snap['pages'][number-1],
            'canvas': snap['manifest']['size'], 'theme': snap['manifest'].get('theme'),
            'assetRoot':str(snap['root']), 'adjacentContext': context(snap, number),
            'image': str(session/state['image']) if state['image'] else None,
            'previewPptx': str(session/state['previewPptx']) if state['previewPptx'] else None,
            'renderer': state['renderer'], 'geometry':state['geometry'], 'typography':state.get('typography'),
            'focus': ('Fix geometry using the editable page and geometry issues; no PPTX is generated until it passes.'
                      if state['geometry']['status']=='blocked' else
                      'Open this page image. Check its claim/evidence and layout; use page patch for one element or page edit for page composition, then inspect the returned image.'),
            'nextCommand': ['ansatz-slide', 'page', 'edit', str(session), '--token', state['token']]}


def check_page(project, number, session, width=1600):
    session = session_path(session)
    if width < 400 or width > 8000: raise ValueError('Width must be 400..8000 pixels')
    with lock(session/'.session.lock'):
        snap = snapshot(project)
        if number < 1 or number > len(snap['pages']): raise ValueError('Page out of range')
        if any(Path(p).is_relative_to(session) for p in snap['tracked']):
            raise ValueError('Session directory must not contain original source files or assets')
        state_path = session/'session.json'
        if state_path.exists():
            old = json.loads(state_path.read_text())
            if old['project'] != str(snap['manifestPath']) or old['page'] != number:
                raise ValueError('Session is pinned to another page/project; use another session directory')
            draft = session/'page.page.yaml'
            if draft.is_file() and sha(draft.read_bytes()) != old.get('draftHash'):
                raise ValueError('Session has an unapplied draft; use page edit or a new session')
        rendered = preview(snap, number, snap['pages'][number-1], session, width)
        state = {'format':1, 'project':str(snap['manifestPath']), 'page':number,
                 'token':page_token(snap, number), 'width':width,
                 'draftHash':sha(json_bytes(snap['pages'][number-1])), **rendered}
        session_write(session, 'page.page.yaml', json_bytes(snap['pages'][number-1]))
        session_write(session, 'session.json', json_bytes(state))
    return response(session, state, snap)


def edit_page(session, token, content=None, *, element_id=None, changes=None):
    session = session_path(session)
    with lock(session/'.session.lock'):
        state_path = session/'session.json'
        state = json.loads(state_path.read_text())
        if state.get('format') != 1: raise ValueError('Unsupported page session')
        project = Path(state['project'])
        with lock(project.parent/'.ansatz-page-edit.lock'):
            snap = snapshot(project); number = state['page']
            if number < 1 or number > len(snap['pages']): raise ValueError('Selected page no longer exists')
            if token != state['token'] or token != page_token(snap, number):
                raise ValueError('Stale page input; run page check again')
            if element_id is not None:
                if content is not None:
                    raise ValueError('Element patch cannot also replace the page')
                draft = session/'page.page.yaml'
                if draft.is_file() and sha(draft.read_bytes()) != state.get('draftHash'):
                    raise ValueError('Session has an unapplied draft; apply it or check in a new session before patching')
                candidate = patch_element(snap['pages'][number-1], element_id, changes)
            else:
                candidate_path = Path(content).resolve() if content else session/'page.page.yaml'
                candidate = parse_document(candidate_path.read_text(encoding='utf-8'), str(candidate_path))
            rendered = preview(snap, number, candidate, session, state['width'])
            from .occupancy import require_pass
            require_pass(rendered['geometry'])
            path = snap['paths'][number-1]
            draft_data = json_bytes(candidate)
            new_data = source_bytes(draft_data)
            session_write(session, 'page.page.yaml', draft_data)
            if not unchanged(snap['tracked']) or not unchanged(rendered['_assetHashes']):
                raise RuntimeError('Concurrent source or asset edit; run page check again')
            publication = preserving_replace(path, new_data, snap['tracked'][str(path)])
            try:
                updated = snapshot(project)
                if (updated['tracked'].get(str(path)) != sha(new_data) or
                        not unchanged({p:h for p,h in snap['tracked'].items() if p != str(path)}) or
                        not unchanged(rendered['_assetHashes'])):
                    raise RuntimeError('Source changed concurrently; edit not accepted')
                new_state = {**state, **rendered, 'token':page_token(updated, number), 'draftHash':sha(draft_data)}
                session_write(session, 'session.json', json_bytes(new_state))
            except Exception:
                publication.rollback()
                raise
    return {**response(session, new_state, updated), 'changedPages':[number],
            'nonTargetSources':'unchanged', 'recoverySource':str(publication.backup), 'effect':'Updated one page source; full-deck PPTX not overwritten. The returned image is the new single-page preview.'}


def check_deck(project):
    snap = snapshot(project)
    return {'project':str(snap['manifestPath']), 'pageCount':len(snap['pages']),
            'outline':[{'page':i+1,'sourcePage':str(snap['paths'][i]), 'title':title(p),
                        'pageType':p.get('pageType')} for i,p in enumerate(snap['pages'])],
            'focus':'Read the whole argument, premises and ending. Expand a specific page with page check when detail is needed; use local edit, split or adjacent merge operations.',
            'editScope':'This command is read-only and does not expose a bulk-edit operation.'}


def reshape_pages(session, token, contents, next_session=None, next_token=None):
    """Split one checked page, or merge two separately checked adjacent pages.

    New sources are staged first; recoverable manifest publication applies the
    new order. Retired sources remain on disk for recovery, outside that order.
    """
    session = session_path(session)
    with lock(session/'.session.lock'):
        state = json.loads((session/'session.json').read_text())
        project = Path(state['project'])
        with lock(project.parent/'.ansatz-page-edit.lock'):
            snap = snapshot(project)
            number = state['page']
            if token != state['token'] or token != page_token(snap, number):
                raise ValueError('Stale page input; run page check again')
            count = 1
            if next_session is not None:
                other = json.loads((session_path(next_session)/'session.json').read_text())
                if other['project'] != str(project) or other['page'] != number+1:
                    raise ValueError('Merge requires the separately checked immediately following page of this project')
                if next_token != other['token'] or next_token != page_token(snap, number+1):
                    raise ValueError('Stale adjacent page input; run page check again')
                count = 2
            if (count == 1 and len(contents) < 2) or (count == 2 and len(contents) != 1):
                raise ValueError('Split requires at least two page objects; merge requires exactly one')
            candidates = [parse_document(Path(p).read_text(encoding='utf-8'), str(p)) for p in contents]
            if any(not isinstance(p, dict) or 'pages' in p for p in candidates):
                raise ValueError('Each content file must contain exactly one page object')
            names = [f'page-{uuid.uuid4().hex}.page.yaml' for _ in candidates]
            manifest = copy.deepcopy(snap['manifest'])
            manifest['pages'][number-1:number-1+count] = names
            pages = snap['pages'][:number-1] + candidates + snap['pages'][number-1+count:]
            validate_project(manifest, pages, snap['root'], check_files=False)
            from .occupancy import require_pages
            require_pages(manifest['size'],pages)
            candidate_assets = {}
            for image in image_objects({'pages':candidates}):
                if not re.match(r'(?i)^(data:|https?://)', image['src']):
                    asset = safe_path(snap['root'], image['src'], 'image')
                    candidate_assets[str(asset)] = sha(asset.read_bytes())
            rendered = [preview(snap, number, p, session, state['width']) for p in candidates]
            from .occupancy import require_pass
            for r in rendered:require_pass(r['geometry'])
            if not unchanged(snap['tracked']) or not unchanged(candidate_assets):
                raise RuntimeError('Concurrent source or asset edit; run page check again')
            publication = publish_order(snap, manifest, dict(zip(names, candidates)), candidate_assets)
            return {'operation':'merge' if count == 2 else 'split',
                    'replacedPages':list(range(number, number+count)),
                    'pageCount':len(pages), 'recoveryManifest':str(publication.backup),
                    'textFit':[r['typography'] for r in rendered],
                    'newPages':[{'page':number+i, 'sourcePage':str(snap['root']/name),
                                 'image':str(session/r['image']), 'previewPptx':str(session/r['previewPptx']), 'geometry':r['geometry']}
                                for i,(name,r) in enumerate(zip(names,rendered))],
                    'retiredSources':[str(p) for p in snap['paths'][number-1:number-1+count]],
                    'effect':'Only this local span was replaced in the manifest order. Existing page files and assets remain unchanged; retired sources are retained. Full-deck PPTX is not overwritten.',
                    'nextCommand':['ansatz-slide','page','check','--project',str(project),
                                   '--page',str(number),'--session',str(session.parent/f'check-{uuid.uuid4().hex[:8]}')]}



def patch_element(page, element_id, changes):
    """Recursively merge fields into exactly one existing element; arrays replace."""
    if not isinstance(changes, dict) or not changes:
        raise ValueError('Changes must be a non-empty object of element fields')
    if {'elementId', 'elementType'} & changes.keys():
        raise ValueError('Patch cannot change element identity or type')
    candidate = copy.deepcopy(page)
    matches = [e for e in candidate.get('elements', []) if e.get('elementId') == element_id]
    if len(matches) != 1:
        raise ValueError('Element ID must identify exactly one element on this page')
    def merge(target, fields):
        for key, value in fields.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = copy.deepcopy(value)
    merge(matches[0], changes)
    return candidate


def checked_state(session, token, snap):
    state = json.loads((session/'session.json').read_text())
    if state.get('format') != 1 or state['project'] != str(snap['manifestPath']):
        raise ValueError('Session must belong to this project')
    number = state['page']
    if (number < 1 or number > len(snap['pages']) or token != state['token']
            or token != page_token(snap, number)):
        raise ValueError('Stale page input; run page check again')
    return state


def publish_order(snap, manifest, new_sources=None, assets=None):
    """Publish source additions and ordered manifest, retaining existing sources."""
    new_sources = new_sources or {}
    from .occupancy import require_pages
    existing=dict(zip(snap['manifest']['pages'],snap['pages']))
    pages=[new_sources[name] if name in new_sources else existing[name] for name in manifest['pages']]
    require_pages(manifest['size'],pages)
    assets = assets or {}
    project = snap['manifestPath']
    created = []
    publication = None
    try:
        if not unchanged(snap['tracked']) or not unchanged(assets):
            raise RuntimeError('Concurrent source or asset edit; run page check again')
        for name, page in new_sources.items():
            path = snap['root']/name
            atomic_write(path, source_bytes(json_bytes(page)), force=False)
            created.append(path)
        if not unchanged(snap['tracked']) or not unchanged(assets):
            raise RuntimeError('Concurrent source or asset edit; run page check again')
        publication = preserving_replace(project, source_bytes(json_bytes(manifest)), snap['tracked'][str(project)])
        if not unchanged(assets) or not unchanged({p:h for p,h in snap['tracked'].items() if p != str(project)}):
            raise RuntimeError('Concurrent source or asset edit during publication; retry page check')
    except Exception:
        if publication is not None: publication.rollback()
        # Keep staged sources if an external manifest may have referenced them.
        # Unreferenced sources are recoverable and never destroy existing data.
        raise
    return publication


def change_order(session, token, operation, *, content=None, position='after',
                 anchor_session=None, anchor_token=None, allow_duplicates=False):
    """Insert next to a checked page, move relative to a checked anchor, or remove."""
    if operation not in ('insert', 'move', 'remove'):
        raise ValueError('Unknown page order operation')
    if position not in ('before', 'after'):
        raise ValueError('Position must be before or after')
    session = session_path(session)
    with lock(session/'.session.lock'):
        initial = json.loads((session/'session.json').read_text())
        project = Path(initial['project'])
        with lock(project.parent/'.ansatz-page-edit.lock'):
            snap = snapshot(project)
            state = checked_state(session, token, snap)
            number = state['page']
            manifest = copy.deepcopy(snap['manifest'])
            order = manifest['pages']
            pages = copy.deepcopy(snap['pages'])
            selected = order[number-1]
            sources, assets, rendered = {}, {}, None
            if operation == 'insert':
                if content is None: raise ValueError('Insert requires one page content file')
                candidate = parse_document(Path(content).read_text(encoding='utf-8'), str(content))
                if not allow_duplicates and any(page_fingerprint(candidate)==page_fingerprint(p) for p in snap['pages']):
                    raise ValueError('Duplicate page content detected; insertion was not published. Use --allow-duplicates only for intentional repetition.')
                for image in image_objects(candidate):
                    if not re.match(r'(?i)^(data:|https?://)', image['src']):
                        asset = safe_path(snap['root'], image['src'], 'image')
                        assets[str(asset)] = sha(asset.read_bytes())
                name = f'page-{uuid.uuid4().hex}.page.yaml'
                index = number if position == 'after' else number-1
                order.insert(index, name); pages.insert(index, candidate)
                sources[name] = candidate
                affected = index+1
            elif operation == 'remove':
                if len(order) == 1:
                    raise ValueError('Cannot remove the last page; projects require at least one page')
                order.pop(number-1); pages.pop(number-1)
                affected = min(number, len(order))
            else:
                if anchor_session is None: raise ValueError('Move requires a checked anchor session')
                anchor = checked_state(session_path(anchor_session), anchor_token, snap)
                if anchor['page'] == number: raise ValueError('Cannot move a page relative to itself')
                anchor_name = order[anchor['page']-1]
                moved = pages.pop(number-1); order.pop(number-1)
                index = order.index(anchor_name) + (position == 'after')
                order.insert(index, selected); pages.insert(index, moved)
                affected = index+1
            validate_project(manifest, pages, snap['root'], check_files=False)
            from .occupancy import require_pages
            require_pages(manifest['size'],pages)
            if operation=='insert':
                rendered = preview(snap, number, candidate, session, state['width'])
            publication = publish_order(snap, manifest, sources, assets)
            result = {'operation':operation, 'pageCount':len(order), 'page':affected,
                      'recoveryManifest':str(publication.backup),
                      'sourcePage':str(snap['root']/order[affected-1]),
                      'existingSources':'unchanged; removed sources retained on disk',
                      'effect':'Updated manifest order; full-deck PPTX is not overwritten.',
                      'nextCommand':['ansatz-slide','page','check','--project',str(project),
                                     '--page',str(affected),'--session',str(session.parent/f'check-{uuid.uuid4().hex[:8]}')]}
            if rendered:
                result.update(image=str(session/rendered['image']), previewPptx=str(session/rendered['previewPptx']), geometry=rendered['geometry'], typography=rendered['typography'])
            if operation == 'move':result['fromPage'] = number
            if operation == 'remove':
                result.update(removedPage=number, removedSource=str(snap['root']/selected))
            return result



def check_overlap(project, number, output, cell_size=1):
    from .occupancy import write_precheck
    snap=snapshot(project)
    if number<1 or number>len(snap['pages']):raise ValueError('Page out of range')
    output=session_path(output)
    if output.exists():raise FileExistsError('Use a new precheck output directory')
    report=write_precheck(snap['manifest']['size'],snap['pages'][number-1],output,cell_size)
    if not unchanged(snap['tracked']):raise RuntimeError('Source changed during precheck; retry')
    return {'page':number,'sourcePage':str(snap['paths'][number-1]),**report}
