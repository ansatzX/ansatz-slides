"""Editable table grids, cell text, borders and merged-cell ownership."""

from .richtext import paragraphs_xml
from .styles import fill_xml, line_xml
from .xml import emu, tag


def cell_style(element, row, column, theme, cell=None):
    reference = element.get("style", {})
    style = (
        theme.get("tableStyles", {}).get(reference.lstrip("$"), {})
        if isinstance(reference, str)
        else reference
    )
    result = {"fontSize": 16, "color": "#333333", "align": ["center", "middle"]}
    result.update(style.get("cellStyle", {}))
    body = style.get("bodyStyles", [])
    if body:
        result.update(body[row % len(body)])
    row_keys = (["firstRowStyle"] if row == 0 else []) + (
        ["lastRowStyle"] if row == len(element["rows"]) - 1 else []
    )
    col_keys = (["firstColumnStyle"] if column == 0 else []) + (
        ["lastColumnStyle"] if column == len(element["columnWidths"]) - 1 else []
    )
    for key in (
        col_keys + row_keys if style.get("rowOverColumn", True) else row_keys + col_keys
    ):
        result.update(style.get(key, {}))
    if cell is None:
        cell = element["rows"][row][column]
    if isinstance(cell, str):
        cell = {"text": cell}
    if cell.get("textStyle"):
        result.update(
            theme.get("textStyles", {}).get(cell["textStyle"].lstrip("$"), {})
        )
    result.update(cell)
    return result


def table_xml(element, theme):
    width, height = element["bounds"][2:]
    body = tag("a:tblPr")
    body += tag(
        "a:tblGrid",
        children="".join(
            tag("a:gridCol", {"w": emu(width * fraction)})
            for fraction in element["columnWidths"]
        ),
    )
    # Source rows omit covered cells. Expand once into physical-grid ownership.
    owners = {}
    origins = {}
    for ri, source_row in enumerate(element["rows"]):
        col = 0
        for cell in source_row:
            while (ri, col) in owners:
                col += 1
            origins[ri, col] = cell
            for dy in range(cell.get("rowSpan", 1)):
                for dx in range(cell.get("colSpan", 1)):
                    owners[ri + dy, col + dx] = (ri, col)
            col += cell.get("colSpan", 1)
    for row_index, row in enumerate(element["rows"]):
        cells = []
        for column in range(len(element["columnWidths"])):
            origin_row, origin_col = owners[row_index, column]
            covered = (origin_row, origin_col) != (row_index, column)
            style = cell_style(
                element, origin_row, origin_col, theme, origins[origin_row, origin_col]
            )
            attrs = {}
            rows, cols = style.get("rowSpan", 1), style.get("colSpan", 1)
            if row_index == origin_row and rows > 1:
                attrs["rowSpan"] = rows
            if column == origin_col and cols > 1:
                attrs["gridSpan"] = cols
            if row_index != origin_row:
                attrs["vMerge"] = 1
            if column != origin_col:
                attrs["hMerge"] = 1
            alignment = style.get("align", ["center", "middle"])
            anchor = {"top": "t", "middle": "ctr", "bottom": "b"}[alignment[1]]
            content = tag(
                "a:bodyPr", {"wrap": "square", "rtlCol": 0, "anchor": anchor}
            ) + tag("a:lstStyle")
            content += paragraphs_xml(
                "" if covered else style.get("text", ""),
                style,
                theme,
                cell=True,
                align=alignment,
            )
            border = style.get("border")
            if isinstance(border, list):
                top, right, bottom, left = border if len(border) == 4 else border * 2
                borders = [left, right, top, bottom]
            else:
                borders = [border] * 4
            properties = "".join(
                line_xml(edge, theme, name)
                for edge, name in zip(borders, ["a:lnL", "a:lnR", "a:lnT", "a:lnB"])
            )
            properties += fill_xml(style.get("fill"), theme)
            content = tag("a:txBody", children=content) + tag(
                "a:tcPr",
                {
                    "marL": 91440,
                    "marR": 91440,
                    "marT": 45720,
                    "marB": 45720,
                    "anchor": None if covered else anchor,
                },
                properties,
            )
            cells.append(tag("a:tc", attrs, content))
        body += tag(
            "a:tr",
            {"h": emu(height * element["rowHeights"][row_index])},
            "".join(cells),
        )
    return tag("a:tbl", children=body)
