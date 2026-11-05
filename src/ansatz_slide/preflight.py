"""Read-only source checks; no Office, PPTX generation, network or image rendering."""
import base64
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote_to_bytes

from .occupancy import check_geometry
from .project import image_objects, load_project, parse_document
from .validation import safe_path, validate_project


class _Text(HTMLParser):
    def __init__(self, value):
        super().__init__(convert_charrefs=True)
        self.parts, self.unformatted, self.script_depth = [], [], 0
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        if tag in ('sub', 'sup'):
            self.script_depth += 1
        if tag in ('p', 'br', 'div', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('sub', 'sup'):
            self.script_depth = max(0, self.script_depth - 1)
        if tag in ('p', 'div', 'li'):
            self.parts.append('\n')

    def handle_data(self, value):
        self.parts.append(value)
        if not self.script_depth:
            self.unformatted.append(value)

    @property
    def text(self):
        return ''.join(self.parts).strip()


_PLAIN_MATH = re.compile(r'(?<![A-Za-z0-9])(?:[στΨψ][A-Za-z][A-Za-z0-9]*|k(?:r|ic|isc)|[ST][01n])(?=$|[^A-Za-z0-9])')
_CITATION = re.compile(r'[A-Za-z\u4e00-\u9fff][^\n]{2,200}[,，][^\n]{1,120}(?:19|20)\d{2}')
_FORMULA_USE = re.compile(r'公式|方程|排序指标|阈值相关指标|截面[—－-]寿命|\b(?:equation|formula)\b', re.I)


def _unicode_math(text):
    return sorted({c for c in text if c == '\u00b5' or c in '\u00b2\u00b3\u00b9'
                   or '\u0370' <= c <= '\u03ff' or '\u2070' <= c <= '\u209f'
                   or '\u2100' <= c <= '\u214f' or '\U0001d400' <= c <= '\U0001d7ff'
                   or ord(c) > 127 and unicodedata.category(c) == 'Sm'})


def _inside(inner, outer):
    x, y, w, h = inner
    a, b, c, d = outer
    return x >= a and y >= b and x + w <= a + c and y + h <= b + d


def analyze(size, pages, root, *, numbers=None, academic=True, allow_remote=True, include_geometry=True, theme=None):
    """Analyze schema-validated pages. Academic hints are not semantic approval."""
    root = Path(root).resolve()
    numbers = list(numbers) if numbers is not None else list(range(1, len(pages) + 1))
    if not numbers or len(numbers) != len(set(numbers)) or any(type(n) is not int or not 1 <= n <= len(pages) for n in numbers):
        raise ValueError('Select distinct existing page numbers')
    issues, summaries = [], []
    def issue(n, code, message, element=None, severity='warning', **details):
        issues.append({'page': n, 'element': element, 'severity': severity,
                       'code': code, 'message': message, **details})

    def resources(value, n, elements):
        assets, formulas = [], []
        for image, path in image_objects(value, with_paths=True):
            owner = elements[path[1]]['elementId'] if len(path) > 1 and path[0] == 'elements' else None
            field = ''.join(f'[{p}]' if isinstance(p, int) else ('.' if i else '') + p
                            for i, p in enumerate(path + ('src',)))
            src = image['src']
            location = {'field': field}
            assets.append({'element': owner, 'field': field, 'src': 'data:<embedded>' if src.startswith('data:') else src})
            if re.match(r'(?i)^https?://', src):
                issue(n, 'remote-asset', 'Remote image was not fetched; prepare a local asset before offline production.', owner,
                      'warning' if allow_remote else 'error', **location)
                continue
            try:
                if src.startswith('data:'):
                    match = re.fullmatch(r'data:([^;,]+)?(;base64)?,(.*)', src, re.S)
                    if not match:
                        raise ValueError('Invalid image data URI')
                    data = base64.b64decode(match[3], validate=True) if match[2] else unquote_to_bytes(match[3])
                    if not data:
                        raise ValueError('Embedded image must be nonempty')
                    continue
                asset_path = safe_path(root, src, 'image.src')
                if not asset_path.is_file() or asset_path.stat().st_size == 0:
                    raise ValueError('Image must be a nonempty local file')
                sources = [p for p in (asset_path.with_suffix('.source.tex'), asset_path.with_suffix('.math.txt'), asset_path.with_suffix('.tex')) if p.is_file()]
                if sources:
                    formulas.append({'element': owner, 'field': field, 'src': src,
                                     'sources': [str(p.relative_to(root)) for p in sources]})
            except (OSError, ValueError) as exc:
                issue(n, 'missing-asset', str(exc), owner, 'error', src='data:<embedded>' if src.startswith('data:') else src, **location)
        return assets, formulas

    shared_assets, _ = resources({'theme': theme or {}}, None, [])

    for n in numbers:
        page = pages[n - 1]
        elements = page['elements']
        texts = [(e, _Text(e['content']['text'])) for e in elements if e['elementType'] == 'text']
        title = next((t.text for e, t in texts if e['elementId'] == 'title'), '')
        if not title:
            title = next((t.text for e, t in texts if e['bounds'][1] < 64), '')
        citations = [t.text for _, t in texts if _CITATION.search(t.text)]
        assets, formulas = resources(page, n, elements)
        geometry = check_geometry(size, page) if include_geometry else {
            'outOfBounds': [], 'unapprovedOverlaps': [], 'invalidDegenerateBounds': []}
        for row in geometry['outOfBounds']:
            issue(n, 'out-of-bounds', 'Element extends beyond the canvas.', row['elementId'], 'error', bounds=row['bounds'])
        for row in geometry['unapprovedOverlaps']:
            issue(n, 'overlap', 'Undeclared element overlap.', severity='error', elements=row['elements'], intersection=row.get('intersection'))
        for ident in geometry['invalidDegenerateBounds']:
            issue(n, 'invalid-bounds', 'Element has invalid zero-area bounds.', ident, 'error')
        if academic:
            if not re.match(r'^\s*[^:：\n]+[:：]\s*\S', title):
                issue(n, 'section-title', 'Use a concise section: page title in the top title area.', 'title')
            if not citations:
                issue(n, 'citation-review', 'No concrete author/venue/year short citation recognized on this page; check each borrowed claim, method, figure and formula.')
            for e, t in texts:
                tokens = sorted({m.group() for part in t.unformatted for m in _PLAIN_MATH.finditer(part)})
                if tokens:
                    issue(n, 'plain-math', 'Possible flattened math indices. Typeset mathematical symbols/indices from LaTeX using the supported equation workflow (PNG + retained TeX); HTML sub/sup alone is not formal math. Review non-mathematical uses manually.', e['elementId'], tokens=tokens)
                if re.search(r'\\(?:frac|sqrt|sigma|tau)\b', e['content']['text']):
                    issue(n, 'latex-review', 'Check whether this LaTeX is actually typeset on the selected production route.', e['elementId'])
            math_texts = [(e['elementId'], t, None) for e, t in texts]
            for index, e in enumerate(elements):
                if e['elementType'] == 'table':
                    for row, cells in enumerate(e['rows']):
                        for col, cell in enumerate(cells):
                            if 'text' in cell:
                                math_texts.append((e['elementId'], _Text(cell['text']),
                                                   f'elements[{index}].rows[{row}][{col}].text'))
            for ident, t, field in math_texts:
                symbols = _unicode_math(t.text)
                if symbols:
                    issue(n, 'unicode-math', 'Possible Unicode math in ordinary text. Typeset mathematical symbols/indices/units from LaTeX; HTML sub/sup alone is not formal math. Review non-mathematical uses manually.',
                          ident, symbols=symbols, **({'field': field} if field else {}))
            prose = '\n'.join(t.text for e, t in texts if e['elementId'] != 'title')
            if _FORMULA_USE.search(title + '\n' + prose) and not formulas:
                issue(n, 'formula-review', 'Mathematical explanation may need a formal formula on this page; no image with adjacent TeX/math source was found. Check native formulas or other legitimate sources manually.')
            for e in elements:
                if e['elementType'] != 'shape' or e.get('shapeName') not in ('rect', 'roundRect'):
                    continue
                _, _, w, h = e['bounds']
                area = w * h / (size[0] * size[1])
                if not .14 <= area <= .7 or h < size[1] * .35:
                    continue
                if any(a['elementType'] in ('image', 'chart', 'table') and _inside(a['bounds'], e['bounds']) for a in elements):
                    continue
                chars = sum(len(re.sub(r'\s+', '', t.text)) for a, t in texts if _inside(a['bounds'], e['bounds']))
                if chars < 70:
                    issue(n, 'sparse-panel', 'Large panel holds little text; consider a compact layout or a meaningful diagram.', e['elementId'], areaFraction=round(area, 3), characters=chars)
        summaries.append({'page': n, 'source': page.get('pagePath'), 'title': title,
                          'citations': citations, 'formulas': formulas, 'assets': assets})
    errors = sum(i['severity'] == 'error' for i in issues)
    warnings = len(issues) - errors
    return {'format': 'source-preflight-v1',
            'status': 'blocked' if errors else 'needs_review' if warnings else 'passed',
            'stage': 'source-only', 'pageCount': len(pages), 'checkedPages': numbers,
            'errors': errors, 'warnings': warnings, 'issues': issues, 'pages': summaries,
            'sharedAssets': shared_assets,
            'notChecked': ['citation accuracy and completeness', 'scientific/mathematical meaning',
                           'argument and layout suitability', 'image pixels/crop contents',
                           'actual fonts, line wrapping and final PPTX appearance']}


def require_pass(report):
    if report['errors']:
        from .validation import ValidationError
        exc = ValidationError('Source preflight failed: ' + '; '.join(
            f"page {i['page']} {i['element'] or ''}: {i['message']}" for i in report['issues'] if i['severity'] == 'error'))
        exc.report = report
        number = next(i['page'] for i in report['issues'] if i['severity'] == 'error')
        if number is not None:
            exc.candidate_number = number
        raise exc


def summary(report):
    """Keep hints in normal command results without repeating all source summaries."""
    return {k: v for k, v in report.items() if k != 'pages'}


def check(source, *, plan=None, settings=None, numbers=None, academic=True, allow_remote=True):
    """Inspect an existing project, or a creation batch without publishing it."""
    if plan is None:
        if settings is not None:
            raise ValueError('--settings requires --plan')
        pptd, root = load_project(source, check_files=False)
        return analyze(pptd['size'], pptd['pages'], root, numbers=numbers,
                       academic=academic, allow_remote=allow_remote, theme=pptd.get('theme'))
    if settings is None:
        raise ValueError('Candidate --plan requires --settings')
    root = Path(source).expanduser().resolve()
    plan = Path(plan).resolve()
    paths = parse_document(plan.read_text(encoding='utf-8'), str(plan))
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p.lower().endswith('.page.yaml') for p in paths):
        raise ValueError('Plan must be a nonempty list of .page.yaml paths, relative to the plan')
    manifest = parse_document(Path(settings).read_text(encoding='utf-8'), str(settings))
    if not isinstance(manifest, dict) or 'pages' in manifest:
        raise ValueError('Settings must be a manifest object without pages')
    pages = [parse_document((plan.parent / p).read_text(encoding='utf-8'), p) for p in paths]
    manifest = {**manifest, 'pages': [f'candidate-{n}.page.yaml' for n in range(1, len(pages) + 1)]}
    validate_project(manifest, pages, root, check_files=False)
    report = analyze(manifest['size'], pages, root, numbers=numbers, academic=academic, allow_remote=allow_remote, theme=manifest.get('theme'))
    for row in report['pages']:
        row['source'] = str((plan.parent / paths[row['page'] - 1]).resolve())
    return report
