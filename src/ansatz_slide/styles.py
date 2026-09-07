"""Theme resolution and DrawingML paint/line/geometry properties."""

import math

from .xml import emu, round_half_away, tag


def color(value, theme=None):
    value = str(value or "#000000")
    if value.startswith("$"):
        value = (theme or {}).get("colors", {}).get(value[1:], "#000000")
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    rgb = value[:6]
    alpha = int(value[6:8], 16) / 255 if len(value) == 8 else 1
    return rgb, alpha


def color_xml(value, theme=None, opacity=1):
    rgb, alpha = color(value, theme)
    return tag(
        "a:srgbClr",
        {"val": rgb},
        tag("a:alpha", {"val": round_half_away(alpha * opacity * 100000)})
        if alpha * opacity < 1
        else None,
    )


def fill_xml(fill, theme=None, opacity=1):
    if isinstance(fill, str):
        fill = {"type": "solid", "color": fill}
    if not fill or fill.get("type") in ["none", "transparent"]:
        return tag("a:noFill")
    if fill.get("type", "solid") == "solid":
        return tag(
            "a:solidFill",
            children=color_xml(fill.get("color", "#000000"), theme, opacity),
        )
    if fill.get("type") == "gradient":
        stops = fill.get("stops", [])
        xml = tag(
            "a:gsLst",
            children="".join(
                tag(
                    "a:gs",
                    {"pos": round_half_away(s["position"] * 100000)},
                    color_xml(s["color"], theme, opacity),
                )
                for s in stops
            ),
        )
        xml += (
            tag("a:path", {"path": "circle"})
            if fill.get("gradientType") == "radial"
            else tag(
                "a:lin",
                {"ang": round_half_away(fill.get("angle", 0) * 60000), "scaled": "1"},
            )
        )
        return tag("a:gradFill", {"rotWithShape": "1"}, xml)
    raise NotImplementedError(
        f"Fill type {fill.get('type')!r} has not been reconstructed"
    )


def line_xml(border, theme=None, name="a:ln", opacity=1):
    if not border or border.get("style") == "none" or border.get("width", 1) == 0:
        return tag(name, children=tag("a:noFill"))
    content = fill_xml(
        {"type": "solid", "color": border.get("color", "#000000")}, theme, opacity
    )
    if border.get("style") in ["dash", "dot"]:
        content += tag("a:prstDash", {"val": border["style"]})
    return tag(name, {"w": emu(border.get("width", 1))}, content)


def transform(bounds, element=None, name="a:xfrm"):
    x, y, width, height = bounds
    el = element or {}
    attrs = {}
    if el.get("rotation"):
        attrs["rot"] = round_half_away(el["rotation"] * 60000)
    if el.get("flip", [False, False])[0]:
        attrs["flipH"] = "1"
    if el.get("flip", [False, False])[1]:
        attrs["flipV"] = "1"
    return tag(
        name,
        attrs,
        tag("a:off", {"x": emu(x), "y": emu(y)})
        + tag("a:ext", {"cx": emu(width), "cy": emu(height)}),
    )


def preset_geometry(name="rect", adjustments=None):
    adjustments = adjustments or []
    values = "".join(
        tag(
            "a:gd",
            {
                "name": "adj" if len(adjustments) == 1 else f"adj{i + 1}",
                "fmla": f"val {round_half_away(v)}",
            },
        )
        for i, v in enumerate(adjustments)
    )
    return tag("a:prstGeom", {"prst": name}, tag("a:avLst", children=values))


def shadow_xml(shadow, theme=None):
    if not shadow:
        return ""
    x, y = shadow.get("offset", [0, 0])
    attrs = {
        "blurRad": emu(shadow.get("blur", 0)),
        "dist": emu(math.hypot(x, y)),
        "dir": round_half_away((math.degrees(math.atan2(y, x)) % 360) * 60000),
        "sx": "100000",
        "sy": "100000",
        "kx": "0",
        "ky": "0",
        "algn": "bl",
        "rotWithShape": "0",
    }
    return tag(
        "a:effectLst",
        children=tag(
            "a:outerShdw", attrs, color_xml(shadow.get("color", "#000000"), theme)
        ),
    )
