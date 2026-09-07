"""Activate the same Python package in a checkout or standalone skill."""
import sys
from pathlib import Path


def activate():
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / "python", here.parents[3] / "src"):
        if (candidate / "ansatz_slide" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    raise RuntimeError("Python core missing: install the complete skill with ansatz-slide install-skill --target <skills-directory>")
