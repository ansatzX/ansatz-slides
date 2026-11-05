"""Editable chart series, literal data caches, axes and chart presentation.

Each chart remains a native PowerPoint chart. Data is serialized as DrawingML
literal caches, matching the existing pptx.yaml writer's workbook-free contract.
"""

import math
from collections import OrderedDict

from .styles import fill_xml, line_xml, shadow_xml
from .xml import NAMESPACES, document, round_half_away, tag, text

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


from .chart_parts import (
    axis_xml,
    data_labels,
    literal,
    marker_xml,
    text_properties,
    title_xml,
    val,
)


def waterfall_values(series, rows):
    encode = series["encode"]
    total = 0
    baselines = []
    heights = []
    roles = []
    extrema = [0]
    for row in rows:
        value = float(row[encode["y"]] or 0)
        is_total = bool(row.get(encode.get("isTotal", "")))
        if is_total:
            end = value
            start = 0
            role = "totalBars"
            total = end
        else:
            start = total
            end = total + value
            total = end
            role = "increaseBars" if value >= 0 else "decreaseBars"
        baselines.append(min(start, end))
        heights.append(abs(end - start))
        roles.append(role)
        extrema.extend([start, end])
    return baselines, heights, roles, extrema


def waterfall_series(series, rows, theme, chart):
    encode = series["encode"]
    categories = [row[encode["x"]] for row in rows]
    baselines, heights, roles, _ = waterfall_values(series, rows)
    name = encode["y"]
    transparent = fill_xml("#FFFFFF00", theme)
    body = val("barDir", "col") + val("grouping", "stacked") + val("varyColors", 0)
    base = (
        val("idx", 0)
        + val("order", 0)
        + tag("c:tx", children=text("c:v", name + "-base"))
    )
    base += tag("c:spPr", children=transparent + tag("a:ln", {"w": 0}, transparent))
    base += literal("cat", categories) + literal("val", baselines, True)
    body += tag("c:ser", children=base)
    visible = val("idx", 1) + val("order", 1) + tag("c:tx", children=text("c:v", name))
    visible += tag("c:spPr", children=fill_xml("#1783FF", theme))
    for index, role in enumerate(roles):
        style = series.get(role, {})
        color = {
            "increaseBars": "#75cc9c",
            "decreaseBars": "#f17c7c",
            "totalBars": "#1783FF",
        }[role]
        visible += tag(
            "c:dPt",
            children=val("idx", index)
            + tag(
                "c:spPr",
                children=fill_xml(style.get("fill", color), theme)
                + line_xml(style.get("border"), theme),
            ),
        )
    from .charts import data_labels

    visible += data_labels(series.get("dataLabels", chart.get("dataLabels")), theme)
    visible += literal("cat", categories) + literal("val", heights, True)
    return body + tag("c:ser", children=visible)


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
