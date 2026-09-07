"""Editable chart series, literal data caches, axes and chart presentation.

Each chart remains a native PowerPoint chart. Data is serialized as DrawingML
literal caches, matching the existing pptx.yaml writer's workbook-free contract.
"""

import math
from collections import OrderedDict

from .styles import fill_xml, line_xml, shadow_xml
from .xml import NAMESPACES, document, number, round_half_away, tag, text

PALETTE = [
    "#1783FF",
    "#68B8A8",
    "#C9A86A",
    "#8C84C9",
    "#8D98A8",
    "#5F9CF5",
    "#7BB6D9",
    "#B28A9E",
    "#333333",
    "#dddddd",
]


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


def series_xml(series, index, rows, theme, chart):
    kind = series["type"]
    encode = series["encode"]
    numeric = kind in ["scatter", "bubble"]
    category_key = encode.get("x", encode.get("category"))
    value_key = encode.get("y", encode.get("value"))
    if series.get("dataFilter"):
        query = series["dataFilter"]
        rows = [row for row in rows if row[query["col"]] == query["value"]]
    if kind == "radar" and rows:
        rows = rows[:1] + rows[:0:-1]
    categories = [row[category_key] for row in rows]
    values = [row[value_key] for row in rows]
    color = (
        series.get("areaColor", PALETTE[index % len(PALETTE)])
        if kind == "radar"
        else PALETTE[index % len(PALETTE)]
    )
    body = (
        val("idx", index)
        + val("order", index)
        + tag("c:tx", children=text("c:v", series.get("name", value_key)))
    )
    fill = series.get("fill", series.get("areaColor", series.get("lineColor", color)))
    if isinstance(fill, list):
        fill = fill[0] if fill else color
    properties = fill_xml(
        fill, theme, 0.7 if kind == "area" and "areaColor" not in series else 1
    )
    if kind in ["line", "area", "radar"]:
        properties += line_xml(
            {
                "width": series.get("width", 2),
                "color": series.get("lineColor", color),
                "style": series.get("lineStyle", "solid"),
            },
            theme,
        )
    elif kind == "scatter":
        properties += line_xml(None)
    elif series.get("border"):
        properties += line_xml(series["border"], theme)
    body += tag("c:spPr", children=properties)
    if kind in ["line", "radar", "scatter"]:
        body += marker_xml(series.get("marker"), color, theme)
    if kind == "pie":
        fills = series.get("fill", PALETTE)
        for position, _ in enumerate(rows):
            fill = fills[position % len(fills)] if isinstance(fills, list) else fills
            body += tag(
                "c:dPt",
                children=val("idx", position)
                + tag(
                    "c:spPr",
                    children=fill_xml(fill, theme)
                    + line_xml(series.get("border"), theme),
                ),
            )
    body += data_labels(series.get("dataLabels"), theme)
    body += literal("xVal" if numeric else "cat", categories, numeric) + literal(
        "yVal" if numeric else "val", values, True
    )
    if kind == "bubble":
        sizes = [float(row[encode["size"]] or 0) for row in rows]
        maximum = max(sizes) or 1
        # PowerPoint bubble sizes are areas; pptx.yaml sizes are normalized diameters.
        minimum_diameter, maximum_diameter = series.get("sizeRange", [8, 50])
        scale = series.get("sizeScale", "sqrt")
        ratios = [max(0, v) / maximum for v in sizes]
        if scale == "sqrt":
            ratios = [math.sqrt(v) for v in ratios]
        elif scale == "log":
            ratios = [math.log1p(max(0, v)) / math.log1p(maximum) for v in sizes]
        normalized = [
            round(
                (minimum_diameter + (maximum_diameter - minimum_diameter) * v) ** 2
                * 0.004,
                4,
            )
            for v in ratios
        ]
        body += literal("bubbleSize", normalized, True)
    if kind == "line":
        body += val("smooth", series.get("smooth", False))
    return tag("c:ser", children=body)


def chart_xml(chart, theme):
    supported = {
        "bar",
        "line",
        "area",
        "scatter",
        "bubble",
        "pie",
        "radar",
        "waterfall",
    }
    for series in chart["series"]:
        if series.get("type") not in supported:
            raise ValueError(f"Unsupported chart series type: {series.get('type')}")

    rows = [dict(zip(chart["data"]["cols"], row)) for row in chart["data"]["rows"]]
    series = [
        {**chart.get("seriesDefaults", {}).get(s["type"], {}), **s}
        for s in chart["series"]
    ]
    groups = OrderedDict()
    for index, item in enumerate(series):
        groups.setdefault(
            (item["type"], item.get("xAxisIndex", 0), item.get("yAxisIndex", 0)), []
        ).append((index, item))
    plot = tag("c:layout")
    axes = OrderedDict()
    for (kind, x_index, y_index), members in groups.items():
        if kind == "waterfall":
            from .waterfall import waterfall_series

            group = waterfall_series(members[0][1], rows, theme, chart)
            output_kind = "bar"
        else:
            output_kind = (
                "doughnut"
                if kind == "pie" and members[0][1].get("innerRadius")
                else kind
            )
            group = ""
            if kind == "bar":
                group += val("barDir", "col")
            if kind in ["bar", "line", "area"]:
                stack = members[0][1].get("stack")
                grouping = (
                    {"normal": "stacked", "value": "stacked", "percent": "stacked"}.get(
                        stack, stack
                    )
                    if stack
                    else ("clustered" if kind == "bar" else "standard")
                )
                group += val("grouping", grouping)
            if kind == "scatter":
                group += val("scatterStyle", "marker")
            if kind == "radar":
                group += val("radarStyle", "marker")
            group += val("varyColors", kind == "pie")
            group += "".join(
                series_xml(s, index, rows, theme, chart) for index, s in members
            )
        group += data_labels(chart.get("dataLabels"), theme)
        if kind in ["bar", "waterfall"]:
            group += val(
                "gapWidth",
                round_half_away((1 / chart["barWidth"] - 1) * 100)
                if chart.get("barWidth")
                else round_half_away(chart.get("categoryGap", 0.56) * 100),
            ) + val(
                "overlap",
                100
                if kind == "waterfall" or members[0][1].get("stack")
                else -round_half_away(chart.get("barGap", 0) * 100),
            )
        if kind == "bubble":
            group += val("bubbleScale", 50) + val("showNegBubbles", 0)
        if kind == "pie":
            group += val(
                "firstSliceAng",
                round_half_away((90 - members[0][1].get("startAngle", 0)) % 360),
            )
            if output_kind == "doughnut":
                group += val(
                    "holeSize", round_half_away(members[0][1]["innerRadius"] * 100)
                )
        else:
            x_id = 1 + x_index
            y_id = 2 + max(s.get("xAxisIndex", 0) for s in series) + y_index
            group += val("axId", x_id) + val("axId", y_id)
            for horizontal, axis_id, cross_id, axis_index in [
                (True, x_id, y_id, x_index),
                (False, y_id, x_id, y_index),
            ]:
                config = chart.get("xAxis" if horizontal else "yAxis", {})
                if isinstance(config, list):
                    config = config[axis_index]
                if kind == "radar" and not horizontal:
                    config = chart.get("spokeAxis", {})
                values = []
                for _, s in members:
                    key = s["encode"].get("x" if horizontal else "y")
                    if key:
                        values.extend(row[key] for row in rows)
                if kind == "waterfall" and not horizontal:
                    from .waterfall import waterfall_values

                    values = waterfall_values(members[0][1], rows)[3]
                if not horizontal and any(s.get("stack") for _, s in members):
                    values = [
                        sum(float(row[s["encode"]["y"]] or 0) for _, s in members)
                        for row in rows
                    ]
                config = {**config, "_secondary": axis_index > 0}
                if axis_id in axes:
                    continue
                axes[axis_id] = (
                    cross_id,
                    config,
                    values,
                    horizontal,
                    horizontal and kind not in ["scatter", "bubble"],
                    kind == "radar",
                )
        plot += tag("c:" + output_kind + "Chart", children=group)
    for axis_id, (
        cross_id,
        config,
        values,
        horizontal,
        category,
        radar,
    ) in axes.items():
        plot += axis_xml(
            axis_id, cross_id, config, values, theme, horizontal, category, radar
        )
    empty = tag("c:spPr", children=tag("a:noFill") + line_xml(None))
    plot += empty
    body = title_xml(chart.get("title"), theme) + tag("c:plotArea", children=plot)
    legend = chart.get(
        "legend", False if any(s["type"] == "waterfall" for s in series) else {}
    )
    if legend is not False and (
        not isinstance(legend, dict) or legend.get("show", True)
    ):
        legend = {} if legend is True else legend
        position = {
            "bottom": "b",
            "top": "t",
            "left": "l",
            "right": "r",
            "top-right": "tr",
        }.get(legend.get("position", "bottom"), "b")
        content = val("legendPos", position) + tag("c:layout") + val("overlay", 0)
        if any(k in legend for k in ["fontSize", "fontFamily", "color"]):
            content += text_properties(legend, theme)
        body += tag("c:legend", children=content)
    body += val("plotVisOnly", 1) + val(
        "dispBlanksAs",
        {"connect": "span", "zero": "zero", "gap": "gap"}.get(
            next((s["nullHandling"] for s in series if "nullHandling" in s), "gap"),
            "gap",
        ),
    )
    properties = (
        fill_xml(chart.get("fill"), theme)
        + line_xml(chart.get("border"), theme)
        + shadow_xml(chart.get("shadow"), theme)
    )
    return document(
        "c:chartSpace",
        {f"xmlns:{key}": NAMESPACES[key] for key in ["c", "a", "r"]},
        val("date1904", 0)
        + tag("c:chart", children=body)
        + tag("c:spPr", children=properties),
    )
