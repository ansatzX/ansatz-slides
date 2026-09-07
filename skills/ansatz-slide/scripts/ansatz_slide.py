#!/usr/bin/env python3
"""Default Python entry point for checkout and installed skill."""
from python_runtime import activate

activate()
from ansatz_slide.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
