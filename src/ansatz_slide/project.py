"""pptx.yaml files -> validated project -> local/HTTP image bytes -> atomic PPTX.

JSON syntax is accepted without third-party packages. YAML uses PyYAML's
pure-Python SafeLoader, with YAML 1.2-style booleans and duplicate-key errors.
"""

import base64
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote_to_bytes
from urllib.request import urlopen

from . import export_pptx
from .validation import ValidationError, array, obj, safe_path, validate_project


def parse_document(text, label):
    try:
        # JSON is a YAML subset, and avoids a YAML dependency entirely.
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValidationError(f"{label}: duplicate key {key!r}")
                result[key] = value
            return result

        return json.loads(
            text,
            object_pairs_hook=unique,
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValidationError(f"{label}: non-finite {x}")
            ),
        )
    except json.JSONDecodeError:
        pass
    try:
        import yaml
    except ImportError as exc:
        raise ValidationError(
            "YAML input requires PyYAML==6.0.3 in a local environment; JSON-formatted documents need only the standard library"
        ) from exc

    class Loader(yaml.SafeLoader):
        yaml_implicit_resolvers = {
            key: [
                (tag, regex)
                for tag, regex in values
                if tag
                not in {
                    "tag:yaml.org,2002:bool",
                    "tag:yaml.org,2002:timestamp",
                    "tag:yaml.org,2002:int",
                    "tag:yaml.org,2002:float",
                }
            ]
            for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
        }

        def construct_mapping(self, node, deep=False):
            result = {}
            for k, v in node.value:
                key = self.construct_object(k, deep=True)
                if not isinstance(key, str):
                    raise ValidationError(
                        f"{label}:{k.start_mark.line + 1}: mapping keys must be strings"
                    )
                if key in result:
                    raise ValidationError(
                        f"{label}:{k.start_mark.line + 1}: duplicate key {key!r}"
                    )
                result[key] = self.construct_object(v, deep=deep)
            return result

    Loader.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
        list("tTfF"),
    )
    Loader.add_implicit_resolver(
        "tag:yaml.org,2002:int",
        re.compile(r"^[-+]?(?:[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"),
        list("-+0123456789"),
    )
    Loader.add_constructor(
        "tag:yaml.org,2002:int",
        lambda loader, node: int(
            loader.construct_scalar(node),
            0 if re.match(r"^[-+]?0[ox]", node.value) else 10,
        ),
    )
    Loader.add_implicit_resolver(
        "tag:yaml.org,2002:float",
        re.compile(
            r"^[-+]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+|\.inf|\.Inf|\.INF|\.nan|\.NaN|\.NAN)$"
        ),
        list("-+0123456789."),
    )
    try:
        value = yaml.load(text, Loader=Loader)
    except yaml.YAMLError as exc:
        raise ValidationError(f"{label}: {exc}") from exc

    # Reject recursive aliases and non-JSON YAML objects before walking them.
    def check_tree(item, ancestors):
        if isinstance(item, (list, dict)):
            if id(item) in ancestors:
                raise ValidationError(f"{label}: recursive YAML alias")
            ancestors = ancestors | {id(item)}
            for child in item.values() if isinstance(item, dict) else item:
                check_tree(child, ancestors)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValidationError(
                f"{label}: unsupported YAML value {type(item).__name__}"
            )

    check_tree(value, set())
    return value


def is_manifest_path(path):
    name = Path(path).name.lower()
    return name == "pptx.yaml" or name.endswith(".pptx.yaml")


def manifest_paths(root):
    """All reserved manifest names, including dangling symlinks."""
    return sorted(path for path in Path(root).iterdir() if is_manifest_path(path))


def find_manifest(source):
    source = Path(source).expanduser().resolve()
    if source.is_file() and is_manifest_path(source):
        return source
    if not source.is_dir():
        raise ValidationError(f"Expected pptx.yaml manifest or project directory: {source}")
    matches = sorted(path for path in source.iterdir() if path.is_file() and is_manifest_path(path))
    if len(matches) != 1:
        raise ValidationError(
            f"Expected exactly one pptx.yaml manifest in {source}, found {len(matches)}; pass a manifest explicitly"
        )
    return matches[0]


def load_project(source, *, check_files=True):
    manifest_path = find_manifest(source)
    return _load_manifest(manifest_path, check_files=check_files)


def _load_manifest(manifest_path, *, check_files=True):
    root = manifest_path.parent
    manifest = parse_document(
        manifest_path.read_text(encoding="utf-8"), str(manifest_path)
    )
    obj(
        manifest,
        "manifest",
        {"version", "title", "customFonts", "size", "theme", "pages"},
        {"version", "size", "pages"},
    )
    array(manifest["pages"], "manifest.pages", minimum=1)
    pages = []
    for rel in manifest["pages"]:
        path = safe_path(root, rel, "manifest.pages")
        if not path.name.lower().endswith(".page.yaml"):
            raise ValidationError(f"Page source must use .page.yaml: {rel}")
        pages.append(parse_document(path.read_text(encoding="utf-8"), str(path)))
    validate_project(manifest, pages, root, check_files=check_files)
    pptd = copy.deepcopy(manifest)
    pptd["pages"] = copy.deepcopy(pages)
    pptd["pptdFileName"] = manifest_path.name
    for rel, page in zip(manifest["pages"], pptd["pages"]):
        page["pagePath"] = rel.replace("\\", "/")
    return pptd, root


def image_objects(value, seen=None, *, with_paths=False):
    """Walk every image resource, including backgrounds, fills and theme styles."""
    seen = set() if seen is None else seen
    def walk(item, path):
        if isinstance(item, (dict, list)):
            if id(item) in seen:
                return
            seen.add(id(item))
        if isinstance(item, dict):
            if item.get('src') and (item.get('elementType') == 'image' or item.get('type') == 'image'):
                yield (item, path) if with_paths else item
            for key, child in item.items():
                yield from walk(child, path + (key,))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                yield from walk(child, path + (index,))
    yield from walk(value, ())


def resolve_images(pptd, root, *, allow_remote=True, timeout=30):
    images, remap = {}, {}
    for value in image_objects(pptd):
        src = value["src"]
        if src not in remap:
            content_type = ""
            if src.startswith("data:"):
                match = re.fullmatch(r"data:([^;,]+)?(;base64)?,(.*)", src, re.S)
                if not match:
                    raise ValidationError("Invalid image data URI")
                content_type = match[1] or ""
                data = (
                    base64.b64decode(match[3], validate=True)
                    if match[2]
                    else unquote_to_bytes(match[3])
                )
            elif re.match(r"^https?://", src, re.I):
                if not allow_remote:
                    raise ValidationError("Remote image disabled by --offline: " + src)
                with urlopen(src, timeout=timeout) as response:
                    data = response.read()
                    content_type = response.headers.get_content_type()
            else:
                data = safe_path(root, src, "image.src").read_bytes()
            if not data:
                raise ValidationError("Empty image: " + src)
            match = re.search(r"\.(png|jpe?g|gif|svg)(?:$|[?#])", src, re.I)
            ext = (
                match[1].lower()
                if match
                else {
                    "image/png": "png",
                    "image/jpeg": "jpg",
                    "image/gif": "gif",
                    "image/svg+xml": "svg",
                }.get(content_type, "png")
            )
            if ext == "jpeg":
                ext = "jpg"
            key = f"wasm-assets/img-{len(images)}.{ext}"  # compatibility resource name, no WASM execution
            images[key] = data
            remap[src] = key
        value["src"] = remap[src]
    return images


SOURCE_HEADER = '# 此文件已存在时，请通过 ansatz-slide CLI 修改，不要直接编辑；请编辑候选文件后由 CLI 校验并写回。\n'


def source_bytes(data):
    """Add an idempotent workflow reminder to formal YAML, not candidate/state files."""
    header = SOURCE_HEADER.encode('utf-8')
    return data if data.startswith(header) else header + data


def atomic_write(destination, data, force=False):
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and not force:
        raise FileExistsError(f"Output exists; use --force: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix="." + destination.name + ".", suffix=".partial", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temporary, destination)
        else:
            # Atomic no-clobber, including a racing creator after preflight.
            os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def create_project(draft, output):
    """Publish a new formal manifest only after all referenced pages pass."""
    draft=Path(draft).expanduser().resolve()
    output=Path(output).expanduser().absolute()
    if output.is_symlink() or output.exists():
        raise FileExistsError('Formal manifest output must be new')
    output=output.resolve()
    if not is_manifest_path(output) or output.parent!=draft.parent:
        raise ValidationError('Output must be pptx.yaml or *.pptx.yaml beside the draft and page sources')
    raw=draft.read_bytes()
    manifest=parse_document(raw.decode('utf-8'),str(draft))
    obj(manifest,'manifest',{'version','title','customFonts','size','theme','pages'}, {'version','size','pages'})
    array(manifest['pages'],'manifest.pages',minimum=1)
    tracked={draft:raw}
    for name in manifest['pages']:
        path=safe_path(draft.parent,name,'manifest.pages')
        tracked[path]=path.read_bytes()
    pptd,root=_load_manifest(draft)
    if output in tracked:
        raise ValidationError('Formal manifest must not overwrite draft or page sources')
    from .occupancy import require_pages
    reports=require_pages(pptd['size'],pptd['pages'])
    if any(path.read_bytes()!=data for path,data in tracked.items()):
        raise RuntimeError('Draft or page source changed during precheck; retry')
    from .page_api import lock, sha
    from .file_transactions import retract_created
    with lock(output.parent/'.ansatz-page-edit.lock'):
        if manifest_paths(output.parent):
            raise ValueError('Project already has a manifest')
        if any(path.read_bytes()!=data for path,data in tracked.items()):
            raise RuntimeError('Draft or page source changed before publication; retry')
        data=source_bytes(raw)
        atomic_write(output,data)
        try:
            if manifest_paths(output.parent)!=[output] or any(path.read_bytes()!=value for path,value in tracked.items()):
                raise RuntimeError('Project changed during publication; retry')
        except Exception:
            retract_created(output,sha(data))
            raise
    return {'output':str(output),'pageCount':len(reports),'geometryStatus':'passed',
            'pages':[{'page':i+1,'status':r['status'],'approvedOverlaps':r['approvedOverlaps']} for i,r in enumerate(reports)],
            'effect':'Created formal manifest after fresh geometry checks; export rechecks current sources.'}


def export_project(
    source, output, *, transition="fade", force=False, allow_remote=True, measure_text=False, backend="native"
):
    if backend not in {"native", "deckcraft"}:
        raise ValidationError("Backend must be native or deckcraft")
    if transition not in {"fade", "none"}:
        raise ValidationError("Transition must be fade or none")
    pptd, root = load_project(source)
    from .occupancy import require_pages
    require_pages(pptd['size'], pptd['pages'])
    from .preflight import analyze, require_pass as require_sources, summary as source_summary
    source_preflight = analyze(pptd['size'], pptd['pages'], root,
                               academic=measure_text, allow_remote=allow_remote, include_geometry=False, theme=pptd.get('theme'))
    require_sources(source_preflight)
    if backend == 'deckcraft':
        from .deckcraft import check_source
        check_source(pptd, transition)
    output = Path(output).expanduser().resolve()
    protected = {find_manifest(source)} | {
        safe_path(root, p["pagePath"], "page") for p in pptd["pages"]
    }
    for image in image_objects(pptd):
        if not re.match(r"(?i)^(data:|https?://)", image["src"]):
            protected.add(safe_path(root, image["src"], "image"))
    if output in protected:
        raise ValidationError("Output must not overwrite source documents or assets")
    if output.exists() and not force:
        raise FileExistsError(f"Output exists; use --force: {output}")
    images = None
    prepared = None
    if backend == 'deckcraft':
        # Compile every field and image format before any Office work. The
        # compiler only constructs commands/paths; it does not create files.
        from .deckcraft import commands_for
        prepared = copy.deepcopy(pptd)
        images = resolve_images(prepared, root, allow_remote=allow_remote)
        commands_for(prepared, images, output.parent, transition)
    text_fit = None
    if measure_text:
        from .typography import check_loaded
        text_fit = check_loaded(pptd, root)
    if prepared is not None:
        pptd = prepared
    else:
        images = resolve_images(pptd, root, allow_remote=allow_remote)
    if backend == "deckcraft":
        from .deckcraft import export_bytes
        output.parent.mkdir(parents=True, exist_ok=True)
        data = export_bytes(pptd, images, output.parent, transition)
    else:
        data = export_pptx(
            pptd,
            {"images": images, "slideTransition": {"effect": transition, "speed": "fast"}},
        )
    from .inspection import inspect_pptx

    report = inspect_pptx(data)
    if report["pageCount"] != len(pptd["pages"]):
        raise ValidationError("Exported page count does not match source")
    atomic_write(output, data, force)
    return {"backend": backend, "output": str(output), "pageCount": len(pptd["pages"]), "structure": report,
            "sourcePreflight": source_summary(source_preflight), **({"textFit":text_fit} if measure_text else {})}
