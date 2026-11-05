"""原生图表字段与系列语义校验。"""

from .common import (
    BASE,
    CHART_TYPES,
    FORMATS,
    array,
    boolean,
    enum,
    fail,
    fields,
    finite,
    number,
    obj,
    string,
    vector,
)


class ChartValidator:
    def title(self, v, at):
        if isinstance(v, str):
            string(v, at, True)
            return
        obj(v, at, {"text", "color", "fontSize", "fontFamily"}, {"text"})
        string(v["text"], at + ".text", True)
        self.chart_font(v, at)

    def chart_font(self, v, at):
        fields(
            v,
            at,
            {
                "color": self.color,
                "fontSize": lambda x, p: number(x, p, positive=True),
                "fontFamily": self.font,
                "numberFormat": lambda x, p: enum(x, p, FORMATS),
            },
        )

    def legend(self, v, at):
        if type(v) is bool:
            return
        obj(v, at, {"show", "position", "color", "fontSize", "fontFamily"})
        self.chart_font(v, at)
        fields(
            v,
            at,
            {
                "show": boolean,
                "position": lambda x, p: enum(x, p, {"top", "bottom", "left", "right"}),
            },
        )

    def labels(self, v, at, contents=("value",)):
        obj(
            v,
            at,
            {"show", "content", "numberFormat", "color", "fontSize", "fontFamily"},
        )
        self.chart_font(v, at)
        fields(
            v, at, {"show": boolean, "content": lambda x, p: enum(x, p, set(contents))}
        )

    def axis(self, v, at, spoke=False):
        keys = {"show", "min", "max", "label", "axisLine", "gridLine"}
        obj(v, at, keys if spoke else keys | {"type", "reverse", "title"})
        fields(
            v,
            at,
            {
                "show": boolean,
                "min": number,
                "max": number,
                "reverse": boolean,
                "title": self.title,
                "type": lambda x, p: enum(x, p, {"category", "value"}),
            },
        )
        if "min" in v and "max" in v and v["min"] >= v["max"]:
            fail(at, "axis min must be less than max")
        if "label" in v and type(v["label"]) is not bool:
            obj(
                v["label"],
                at + ".label",
                {"color", "fontSize", "fontFamily", "numberFormat"},
            )
            self.chart_font(v["label"], at + ".label")
        for key in ("axisLine", "gridLine"):
            if key in v and type(v[key]) is not bool:
                self.border(
                    v[key], at + "." + key, arrow=not spoke and key == "axisLine"
                )

    def marker(self, v, at, allow_false):
        if v is False and allow_false:
            return
        obj(v, at, {"shape", "fill", "border", "size"})
        fields(
            v,
            at,
            {
                "shape": lambda x, p: enum(
                    x, p, {"circle", "rect", "diamond", "triangle"}
                ),
                "fill": self.series_fill,
                "border": self.border,
                "size": lambda x, p: number(x, p, positive=True),
            },
        )

    def series(self, v, at, kind, cols, rows, defaults=False):
        common = {"type", "encode", "name", "xAxisIndex", "yAxisIndex", "dataLabels"}
        lines = {"smooth", "lineStyle", "width", "marker", "nullHandling", "lineColor"}
        allowed = {
            "bar": common | {"stack", "symbol", "fill", "border"},
            "line": common | lines,
            "area": common | lines | {"stack", "areaColor"},
            "radar": common | lines | {"areaColor"},
            "scatter": common | {"dataFilter", "marker", "fill", "border"},
            "bubble": common
            | {"dataFilter", "sizeScale", "sizeRange", "fill", "border"},
            "pie": {
                "type",
                "encode",
                "innerRadius",
                "startAngle",
                "fill",
                "border",
                "dataLabels",
            },
            "waterfall": {
                "type",
                "encode",
                "totalBars",
                "increaseBars",
                "decreaseBars",
                "dataLabels",
            },
        }[kind]
        obj(v, at, allowed, set() if defaults else {"type", "encode"})
        if defaults and ("type" in v or "encode" in v):
            fail(at, "seriesDefaults cannot contain type or encode")
        if not defaults:
            enum(v["type"], at + ".type", {kind})
            required = {
                "pie": {"category", "value"},
                "radar": {"category", "y"},
                "bubble": {"x", "y", "size"},
            }.get(kind, {"x", "y"})
            optional = {"isTotal"} if kind == "waterfall" else set()
            enc = v["encode"]
            obj(enc, at + ".encode", required | optional, required)
            numeric = {
                "scatter": {"x", "y"},
                "bubble": {"x", "y", "size"},
                "pie": {"value"},
            }.get(kind, {"y"})
            for channel, col in enc.items():
                string(col, at + ".encode." + channel, True)
                if col not in cols:
                    fail(at, f"unknown data column {col!r}")
                for row in rows:
                    cell = row[cols.index(col)]
                    if cell is None:
                        continue
                    if channel in numeric and not finite(cell):
                        fail(at, "numeric channel contains a non-numeric value")
                    if channel == "isTotal" and type(cell) is not bool:
                        fail(at, "isTotal channel must be boolean")
                    if channel == "category" and not (
                        isinstance(cell, str) or finite(cell)
                    ):
                        fail(at, "category channel must be string or number")
        fields(
            v,
            at,
            {
                "name": lambda x, p: string(x, p, True),
                "xAxisIndex": lambda x, p: number(x, p, minimum=0, integer=True),
                "yAxisIndex": lambda x, p: number(x, p, minimum=0, integer=True),
                "smooth": boolean,
                "lineStyle": lambda x, p: enum(x, p, {"solid", "dash", "dot"}),
                "width": lambda x, p: number(x, p, positive=True),
                "nullHandling": lambda x, p: enum(x, p, {"zero", "gap", "connect"}),
                "lineColor": self.series_fill,
                "areaColor": self.series_fill,
                "stack": lambda x, p: enum(x, p, {"value", "percent"}),
                "symbol": self.shape,
                "border": self.border,
                "sizeScale": lambda x, p: enum(x, p, {"linear", "sqrt", "log"}),
                "innerRadius": lambda x, p: number(x, p, minimum=0, maximum=1),
                "startAngle": lambda x, p: number(
                    x, p, minimum=0, maximum=360, exclusive_max=True
                ),
            },
        )
        if "fill" in v:
            self.series_fill(v["fill"], at + ".fill", collection=kind == "pie")
        if "marker" in v:
            self.marker(v["marker"], at + ".marker", kind in {"line", "area", "radar"})
        if "dataLabels" in v:
            labels = {
                "pie": ("value", "percentage", "category"),
                "waterfall": ("value", "category"),
            }.get(kind, ("value",))
            self.labels(v["dataLabels"], at + ".dataLabels", labels)
        if "dataFilter" in v:
            f = v["dataFilter"]
            obj(f, at + ".dataFilter", {"col", "value"}, {"col", "value"})
            string(f["col"], at, True)
            if f["col"] not in cols or not (
                isinstance(f["value"], str) or finite(f["value"])
            ):
                fail(at, "invalid dataFilter")
        if "sizeRange" in v:
            vector(v["sizeRange"], at + ".sizeRange", 2, positive=True)
            if v["sizeRange"][0] >= v["sizeRange"][1]:
                fail(at, "size range min must be less than max")
        for key in ("totalBars", "increaseBars", "decreaseBars"):
            if key in v:
                obj(v[key], at + "." + key, {"fill", "border"})
                fields(
                    v[key],
                    at + "." + key,
                    {"fill": self.series_fill, "border": self.border},
                )

    def chart(self, v, at):
        obj(
            v,
            at,
            BASE
            | {
                "data",
                "series",
                "seriesDefaults",
                "xAxis",
                "yAxis",
                "barWidth",
                "barGap",
                "categoryGap",
                "spokeAxis",
                "title",
                "legend",
                "dataLabels",
                "fontFamily",
                "fill",
                "border",
                "shadow",
            },
            {"data", "series"},
        )
        data = v["data"]
        obj(data, at + ".data", {"cols", "rows"}, {"cols", "rows"})
        cols, rows = data["cols"], data["rows"]
        array(cols, at + ".data.cols", minimum=1)
        for c in cols:
            string(c, at + ".data.cols", True)
        if len(set(cols)) != len(cols):
            fail(at, "duplicate data column")
        array(rows, at + ".data.rows")
        for row in rows:
            array(row, at + ".data.rows", len(cols))
            for cell in row:
                if (
                    cell is not None
                    and not isinstance(cell, (str, bool))
                    and not finite(cell)
                ):
                    fail(at, "invalid data cell")
        array(v["series"], at + ".series", minimum=1)
        types = []
        for i, s in enumerate(v["series"]):
            obj(s, at + ".series", set(s) if isinstance(s, dict) else (), {"type"})
            enum(s["type"], at + ".series.type", CHART_TYPES)
            types.append(s["type"])
            self.series(s, f"{at}.series[{i}]", s["type"], cols, rows)
        if (
            any(t in {"pie", "waterfall"} for t in types)
            and len(types) != 1
            or "radar" in types
            and set(types) != {"radar"}
        ):
            fail(at, "exclusive chart types cannot be mixed or repeated")
        for kind in ("bar", "area"):
            if (
                len(
                    {
                        s["stack"]
                        for s in v["series"]
                        if s["type"] == kind and "stack" in s
                    }
                )
                > 1
            ):
                fail(at, "stacked series must share stack mode")
        if (
            len({s["encode"]["category"] for s in v["series"] if s["type"] == "radar"})
            > 1
        ):
            fail(at, "radar series must share category column")
        if "seriesDefaults" in v:
            obj(
                v["seriesDefaults"],
                at + ".seriesDefaults",
                {"bar", "line", "area", "scatter", "bubble", "radar"},
            )
            for kind, s in v["seriesDefaults"].items():
                self.series(s, at + ".seriesDefaults." + kind, kind, cols, rows, True)
        for key in ("xAxis", "yAxis"):
            if key in v:
                axes = v[key] if isinstance(v[key], list) else [v[key]]
                for a in axes:
                    self.axis(a, at + "." + key)
            for s in v["series"]:
                index = s.get(key + "Index", 0)
                if index > 0 and (
                    not isinstance(v.get(key), list) or len(v[key]) <= index
                ):
                    fail(at, key + " must be long enough for series index")
        fields(
            v,
            at,
            {
                "title": self.title,
                "legend": self.legend,
                "dataLabels": lambda x, p: self.labels(
                    x, p, ("value", "percentage", "category")
                ),
                "fontFamily": self.font,
                "fill": self.fill,
                "border": self.border,
                "shadow": self.shadow,
                "spokeAxis": lambda x, p: self.axis(x, p, True),
                "barWidth": lambda x, p: number(x, p, positive=True, maximum=1),
                "barGap": lambda x, p: number(
                    x, p, minimum=0, maximum=1, exclusive_max=True
                ),
                "categoryGap": lambda x, p: number(
                    x, p, minimum=0, maximum=1, exclusive_max=True
                ),
            },
        )
        applicable = {
            "xAxis": {"bar", "line", "area", "scatter", "bubble", "waterfall"},
            "yAxis": {"bar", "line", "area", "scatter", "bubble", "waterfall"},
            "barWidth": {"bar", "waterfall"},
            "barGap": {"bar", "waterfall"},
            "categoryGap": {"bar", "waterfall"},
            "spokeAxis": {"radar"},
        }
        for key, kinds in applicable.items():
            if key in v and not kinds.intersection(types):
                fail(at + "." + key, "field not applicable to chart type")
