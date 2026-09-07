"""Small explicit OOXML serializer; attribute order and empty tags are deterministic."""

import math
from html import escape

DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "a14": "http://schemas.microsoft.com/office/drawing/2010/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "pptd": "https://kimi-design.msh.team/pptd/2026",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def number(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def tag(name, attrs=None, children=None):
    attributes = "".join(
        f' {key}="{escape(number(value), quote=True)}"'
        for key, value in (attrs or {}).items()
        if value is not None
    )
    if children is None or children == "":
        return f"<{name}{attributes}/>"
    return f"<{name}{attributes}>{children}</{name}>"


def text(name, value, attrs=None):
    return tag(name, attrs, escape(str(value), quote=False))


def document(name, attrs=None, children=None):
    return DECLARATION + tag(name, attrs, children)


def round_half_away(value):
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)


def emu(points):
    return round_half_away(float(points) * 12700)
