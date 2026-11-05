"""原生图表共用的轴、标题、标记和数据缓存 XML。"""

import math

from .styles import fill_xml, line_xml
from .xml import number, round_half_away, tag, text


def val(name, value):
    return tag("c:" + name, {"val": value})


def literal(name, values, numeric=False):
    content = text("c:formatCode", "General") if numeric else ""
    content += val("ptCount", len(values))
    content += "".join(
        tag(
            "c:pt",
            {"idx": index},
            text("c:v", number(value) if value is not None else ""),
        )
        for index, value in enumerate(values)
    )
    return tag(
        "c:" + name,
        children=tag("c:numLit" if numeric else "c:strLit", children=content),
    )


def font_properties(style, theme):
    font = style.get("fontFamily", "Arial")
    if isinstance(font, dict):
        font = font.get("latin", "Arial")
    attrs = {
        "sz": round_half_away(style.get("fontSize", 12) * 100),
        "noProof": 1,
        "b": 0,
        "i": 0,
        "u": "none",
        "strike": "noStrike",
    }
    return tag(
        "a:defRPr",
        attrs,
        fill_xml(style.get("color", "#000000"), theme)
        + tag("a:latin", {"typeface": font}),
    )


def text_properties(style, theme):
    para = tag("a:pPr", children=font_properties(style, theme)) + tag(
        "a:endParaRPr", {"lang": "en-US", "noProof": 1}
    )
    return tag(
        "c:txPr",
        children=tag("a:bodyPr") + tag("a:lstStyle") + tag("a:p", children=para),
    )


def title_xml(title, theme):
    if not title:
        return ""
    title = {"text": title} if isinstance(title, str) else title
    attrs = {"lang": "en-US", "noProof": 1}
    properties = ""
    if "fontSize" in title:
        attrs["sz"] = round_half_away(title["fontSize"] * 100)
    if "color" in title:
        properties += fill_xml(title["color"], theme)
    if "fontFamily" in title:
        font = title["fontFamily"]
        font = font.get("latin", "Arial") if isinstance(font, dict) else font
        properties += tag("a:latin", {"typeface": font})
    run = tag(
        "a:r",
        children=tag("a:rPr", attrs, properties) + text("a:t", title.get("text", "")),
    )
    rich = tag("a:bodyPr") + tag("a:lstStyle") + tag("a:p", children=run)
    return tag(
        "c:title",
        children=tag("c:tx", children=tag("c:rich", children=rich)) + val("overlay", 0),
    )


def axis_range(values, config):
    values = [float(v) for v in values if v is not None]
    lower = min([0] + values)
    upper = max([0] + values)
    if lower == upper:
        upper = lower + 1
    rough = (upper - lower) / 6
    magnitude = 10 ** math.floor(math.log10(rough))
    normalized = rough / magnitude
    # The original writer uses six preferred intervals per decade.
    interval = (
        next((step for step in [1, 2, 3, 5, 10] if step >= normalized), 10) * magnitude
    )
    lower = math.floor(lower / interval) * interval
    upper = math.ceil(upper / interval) * interval
    return config.get("min", lower), config.get("max", upper), interval


def axis_xml(
    axis_id,
    cross_id,
    config,
    values,
    theme,
    horizontal=False,
    category=False,
    radar=False,
):
    config = {"show": config} if isinstance(config, bool) else (config or {})
    scaling = val("orientation", "maxMin" if config.get("reverse") else "minMax")
    if not category:
        lower, upper, interval = axis_range(values, config)
        scaling += val("max", upper) + val("min", lower)
    body = (
        val("axId", axis_id)
        + tag("c:scaling", children=scaling)
        + val("delete", not config.get("show", True))
        + val(
            "axPos",
            ("t" if config.get("_secondary") else "b")
            if horizontal
            else ("r" if config.get("_secondary") else "l"),
        )
    )
    grid = config.get(
        "gridLine", False if horizontal else {"width": 1, "color": "#E0E6F1"}
    )
    if grid is not False or "gridLine" in config:
        body += tag(
            "c:majorGridlines",
            children=tag(
                "c:spPr", children=line_xml(grid if grid is not False else None, theme)
            ),
        )
    if config.get("title"):
        title = config["title"]
        title = {"text": title} if isinstance(title, str) else title
        title = title_xml({"fontSize": 12, **title}, theme)
        layout = tag(
            "c:layout",
            children=tag(
                "c:manualLayout",
                children=val("xMode", "edge")
                + val("yMode", "edge")
                + val("x", 0.48 if horizontal else 0.02)
                + val("y", 0.82 if horizontal else 0.44),
            ),
        )
        body += title.replace("<c:overlay", layout + "<c:overlay")
    label = config.get("label", {})
    label = {} if label is True else label
    hidden = label is False or (radar and not horizontal and "label" not in config)
    if label is False:
        label = {}
    body += tag(
        "c:numFmt",
        {
            "formatCode": label.get("numberFormat", "General"),
            "sourceLinked": 1 if horizontal else 0,
        },
    )
    body += (
        val("majorTickMark", "out")
        + val("minorTickMark", "none")
        + val("tickLblPos", "none" if hidden else ("low" if horizontal else "nextTo"))
    )
    border = config.get("axisLine", {"width": 1, "color": "#888888"})
    body += tag(
        "c:spPr", children=line_xml(border if border is not False else None, theme)
    ) + text_properties(label, theme)
    body += val("crossAx", cross_id) + val(
        "crosses", "max" if config.get("_secondary") else "autoZero"
    )
    if category:
        body += val("auto", 1) + val("lblAlgn", "ctr") + val("noMultiLvlLbl", 1)
    else:
        body += val("crossBetween", "midCat" if horizontal else "between")
        if "min" not in config or "max" not in config:
            body += val("majorUnit", interval)
    return tag("c:catAx" if category else "c:valAx", children=body)


def marker_xml(marker, color, theme):
    if marker is False:
        return tag("c:marker", children=val("symbol", "none"))
    marker = marker or {}
    body = val(
        "symbol",
        {"rect": "square"}.get(
            marker.get("shape", "circle"), marker.get("shape", "circle")
        ),
    ) + val("size", round_half_away(marker.get("size", 6)))
    body += tag(
        "c:spPr",
        children=fill_xml(marker.get("fill", color), theme)
        + line_xml(marker.get("border", {"width": 0.75, "color": color}), theme),
    )
    return tag("c:marker", children=body)


def data_labels(style, theme):
    if style is None or style is False:
        return ""
    style = {"show": style} if isinstance(style, bool) else style
    show = style.get("show", True)
    body = ""
    if "numberFormat" in style:
        body += tag(
            "c:numFmt", {"formatCode": style["numberFormat"], "sourceLinked": 0}
        )
    if any(k in style for k in ["color", "fontSize", "fontFamily"]):
        body += text_properties(style, theme)
    body += val("dLblPos", "ctr")
    for name, key in [
        ("showLegendKey", None),
        ("showVal", "value"),
        ("showCatName", "category"),
        ("showSerName", None),
        ("showPercent", "percentage"),
        ("showBubbleSize", None),
    ]:
        body += val(name, show and key == style.get("content", "value"))
    return tag("c:dLbls", children=body)
