"""Waterfall charts as an invisible baseline plus editable stacked bars."""

from .charts import literal, val
from .styles import fill_xml, line_xml
from .xml import tag, text


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
