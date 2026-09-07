"""Readable pptx.yaml → editable PPTX source implementation.

No generated C, WASM engine, Node addon or binary writer is used here.
"""

from .package import Package
from .slides import SlideWriter


def export_pptx(pptd, options=None):
    """Return PPTX bytes for an in-memory presentation object and resolved resources."""
    if not isinstance(pptd, dict) or not isinstance(pptd.get("pages"), list):
        raise ValueError("pptx.yaml pages must be an array")
    options = options or {}
    package = Package()
    for number, page in enumerate(pptd["pages"], 1):
        SlideWriter(
            package,
            number,
            pptd.get("theme", {}),
            options.get("images", {}),
            pptd.get("size", [960, 540]),
            options.get("slideTransition", options.get("transition")),
        ).write(page)
    return package.finish(pptd.get("size", [960, 540]), len(pptd["pages"]))
