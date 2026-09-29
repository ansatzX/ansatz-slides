#!/usr/bin/env python3
"""Check built distribution contents without installing or executing them."""
import argparse
import json
import tarfile
from pathlib import Path
from zipfile import ZipFile

FORBIDDEN = {'legacy', 'research', 'node_modules', 'tmp', '__pycache__', '.venv', '.scripts', '.state-machine'}


def check_names(names, *, wheel):
    for name in names:
        parts = set(Path(name).parts)
        if parts & FORBIDDEN or name.endswith(('.pyc', '.wasm', '.mjs')):
            raise ValueError(f'Unexpected runtime artifact: {name}')
        if wheel and 'tests' in parts:
            raise ValueError(f'Tests leaked into wheel: {name}')


def required_files(root):
    """Derive the archive contract from the complete maintained source tree."""
    runtime = {str(p.relative_to(root/'src')) for p in (root/'src/ansatz_slide').rglob('*.py')}
    skill = {'ansatz_slide/skill/'+str(p.relative_to(root/'skills/ansatz-slide'))
             for p in (root/'skills/ansatz-slide').rglob('*')
             if p.is_file() and not (set(p.relative_to(root/'skills/ansatz-slide').parts) & FORBIDDEN) and p.suffix in ('.py','.md','.lock')}
    tests = {str(p.relative_to(root)) for p in (root/'tests').rglob('*.py')}
    return runtime | skill, tests


def require_present(names, required):
    missing = sorted(set(required)-set(names))
    if missing: raise ValueError('Missing distribution files: '+', '.join(missing))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--sdist', required=True, type=Path)
    args = parser.parse_args()
    required, tests = required_files(Path(__file__).resolve().parents[1])
    with ZipFile(args.wheel) as wheel:
        names = wheel.namelist()
        check_names(names, wheel=True)
        require_present(names, required)
        for resource in ('ansatz_slide/cli.py', 'ansatz_slide/shape_names.txt',
                         'ansatz_slide/templates/ppt/theme/theme1.xml',
                         'ansatz_slide/skill/SKILL.md', 'ansatz_slide/skill/runtime.lock'):
            if resource not in names:
                raise ValueError(f'Missing package data: {resource}')
    with tarfile.open(args.sdist) as sdist:
        source_names = sdist.getnames()
        check_names(source_names, wheel=False)
        relative_names = {name.split('/',1)[1] for name in source_names if '/' in name}
        require_present(relative_names, tests | {'src/'+p for p in required if not p.startswith('ansatz_slide/skill/')} |
                        {'skills/ansatz-slide/'+p.removeprefix('ansatz_slide/skill/') for p in required if p.startswith('ansatz_slide/skill/')})
        if not any(name.endswith('/tests/core/test_workflow.py') for name in source_names):
            raise ValueError('Source distribution must carry core workflow tests')
    print(json.dumps({'ok': True, 'wheelFiles': len(names), 'wheelBytes': args.wheel.stat().st_size,
                      'sourceFiles': len(source_names), 'sourceBytes': args.sdist.stat().st_size}))


if __name__ == '__main__':
    main()
