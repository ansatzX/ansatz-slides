#!/usr/bin/env python3
"""Typeset trusted math with local pdfLaTeX/Poppler; no core exporter dependency."""
import argparse
import json
import math
import os
import hashlib
import uuid
import stat
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import struct


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def publish_pair(pairs, expected, force):
    """Keep old versions and roll back both outputs on a publication error."""
    folder = pairs[0][1].parent/'.ansatz-equations'
    if folder.is_symlink(): raise ValueError('Equation recovery directory must not be a symlink')
    recovery = folder/uuid.uuid4().hex
    recovery.mkdir(parents=True)
    backups, published = {}, {}
    try:
        for staged, target in pairs:
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError('Equation outputs must be regular files')
            if file_hash(target) != expected[target]:
                raise RuntimeError('Equation output changed during rendering')
            if target.exists():
                if not force: raise FileExistsError('Output exists; use --force')
                staged.chmod(stat.S_IMODE(target.stat().st_mode))
                backup = recovery/(target.name+'.previous')
                os.rename(target, backup)
                backups[target] = backup
                if file_hash(backup) != expected[target]:
                    raise RuntimeError('Equation output changed during publication')
        for staged, target in pairs:
            os.link(staged, target)
            published[target] = file_hash(staged)
    except Exception as exc:
        for target, value in published.items():
            if target.exists() and not target.is_symlink():
                displaced = recovery/(target.name+'.displaced')
                os.rename(target, displaced)
                if file_hash(displaced) != value:
                    try: os.link(displaced, target)
                    except FileExistsError: pass
        for target, backup in backups.items():
            try: os.link(backup, target)
            except FileExistsError: pass
        raise RuntimeError(f'Equation publication failed; recovery files retained at {recovery}: {exc}') from exc


def render(expression, output, box=None, force=False, pixels=2400):
    expression, output = Path(expression).resolve(), Path(output).absolute()
    if output.is_symlink() or output.with_suffix('.source.tex').is_symlink():
        raise ValueError('Equation outputs must not be symlinks')
    if output.suffix.lower() != '.png':
        raise ValueError('Output must have a .png suffix')
    source_output = output.with_suffix('.source.tex')
    if expression in (output, source_output):
        raise ValueError('Input expression must be separate from generated outputs')
    if not force and (output.exists() or source_output.exists()):
        raise FileExistsError('Output exists; use --force to replace generated assets')
    if box is not None and (len(box) != 4 or not all(math.isfinite(v) for v in box)
                            or box[2] <= 0 or box[3] <= 0):
        raise ValueError('Box needs finite x y and positive width height')
    expected = {p:file_hash(p) for p in (output, source_output)}
    body = expression.read_text(encoding='utf-8').strip()
    if not body:
        raise ValueError('Math expression is empty')
    if pixels <= 0:
        raise ValueError('Pixel extent must be positive')
    programs = {p: shutil.which(p) for p in ('pdflatex', 'pdftocairo')}
    missing = [p for p, path in programs.items() if path is None]
    if missing:
        raise RuntimeError('Missing local executable(s): ' + ', '.join(missing))
    source = ('\\documentclass[border=4pt]{standalone}\n'
              '\\usepackage{amsmath,amssymb,bm}\n\\begin{document}\n'
              '$\\displaystyle ' + body + '$\n\\end{document}\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.equation-', dir=output.parent) as scratch:
        work = Path(scratch)
        (work / 'equation.tex').write_text(source, encoding='utf-8')
        extent = math.ceil(max(box[2:]) * 4) if box is not None else pixels
        commands = [
            [programs['pdflatex'], '-no-shell-escape', '-interaction=nonstopmode',
             '-halt-on-error', 'equation.tex'],
            [programs['pdftocairo'], '-singlefile', '-png', '-transp',
             '-scale-to', str(extent), 'equation.pdf', 'equation'],
        ]
        for command in commands:
            run = subprocess.run(command, cwd=work, capture_output=True, text=True,
                                 timeout=60, check=False)
            if run.returncode:
                raise RuntimeError(Path(command[0]).name + ' failed:\n' +
                                   (run.stdout + run.stderr)[-3000:])
        png = work / 'equation.png'
        data = png.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Renderer did not produce PNG')
        width_px, height_px = struct.unpack('>II', data[16:24])
        if min(width_px, height_px) <= 0:
            raise ValueError('Invalid PNG dimensions')
        result = {'png': str(output), 'tex_source': str(source_output),
                  'pixels': [width_px, height_px], 'typesetter': 'pdflatex + pdftocairo',
                  'office_editability': 'image', 'visual_review': 'not performed'}
        if box is not None:
            x, y, w, h = box
            scale = min(w / width_px, h / height_px)
            width, height = width_px * scale, height_px * scale
            result['bounds'] = [x + (w-width)/2, y + (h-height)/2, width, height]
        # Replace only after successful conversion and validation.
        publish_pair([(work/'equation.tex', source_output), (png, output)], expected, force)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expression', type=Path)
    parser.add_argument('-o', '--output', required=True, type=Path)
    parser.add_argument('--box', nargs=4, type=float, metavar=('X', 'Y', 'W', 'H'))
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--pixels', type=int, default=2400, help='longest PNG edge without --box; with --box use 4 pixels per slide unit')
    args = parser.parse_args()
    try:
        result = render(args.expression, args.output, args.box, args.force, args.pixels)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
