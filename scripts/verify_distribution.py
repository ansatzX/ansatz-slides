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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--sdist', required=True, type=Path)
    args = parser.parse_args()
    with ZipFile(args.wheel) as wheel:
        names = wheel.namelist()
        check_names(names, wheel=True)
        for required in ('ansatz_slide/cli.py', 'ansatz_slide/shape_names.txt',
                         'ansatz_slide/templates/ppt/theme/theme1.xml',
                         'ansatz_slide/skill/SKILL.md', 'ansatz_slide/skill/runtime.lock'):
            if required not in names:
                raise ValueError(f'Missing package data: {required}')
    with tarfile.open(args.sdist) as sdist:
        source_names = sdist.getnames()
        check_names(source_names, wheel=False)
        if not any(name.endswith('/tests/core/test_workflow.py') for name in source_names):
            raise ValueError('Source distribution must carry core workflow tests')
    print(json.dumps({'ok': True, 'wheelFiles': len(names), 'wheelBytes': args.wheel.stat().st_size,
                      'sourceFiles': len(source_names), 'sourceBytes': args.sdist.stat().st_size}))


if __name__ == '__main__':
    main()
