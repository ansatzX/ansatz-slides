#!/usr/bin/env python3
"""Default Python entry point for checkout and installed skill."""

import sys
from pathlib import Path

here = Path(__file__).resolve()
for candidate in (here.parents[1] / "python", here.parents[3] / "src"):
    if (candidate / "ansatz_slide" / "__init__.py").is_file():
        sys.path.insert(0, str(candidate))
        break
else:
    raise RuntimeError(
        "Python core missing: install the complete skill with ansatz-slide install-skill --target <skills-directory>"
    )

from ansatz_slide.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
