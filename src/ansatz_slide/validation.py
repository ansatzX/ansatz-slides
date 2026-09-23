"""Strict project validation, independent of JavaScript and the PPTX serializer.

Rules deliberately reject unknown fields and unsupported writer semantics.
Errors carry the document path. The first error aborts before resource fetching
or output replacement; callers must not retry by bypassing this gate.
"""

import math
import re
from pathlib import Path


class ValidationError(ValueError):
    pass


def fail(at, message):
    raise ValidationError(f"pptx.yaml validation failed: {at}: {message}")


def obj(v, at, keys, required=()):
    if not isinstance(v, dict):
        fail(at, "expected object")
    for key in v:
        if key not in keys:
            fail(at, f"unknown field {key!r}")
    for key in required:
        if key not in v:
            fail(at, f'missing required field "{key}"')


def string(v, at, nonempty=False):
    if not isinstance(v, str) or (nonempty and not v.strip()):
        fail(at, "expected a non-empty string" if nonempty else "expected string")


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def number(
    v,
    at,
    minimum=None,
    maximum=None,
    positive=False,
    exclusive_max=False,
    integer=False,
):
    if not finite(v):
        fail(at, "expected finite number")
    if positive and v <= 0 or minimum is not None and v < minimum:
        fail(at, "number is below permitted range")
    if maximum is not None and (v >= maximum if exclusive_max else v > maximum):
        fail(at, "number is above permitted range")
    if integer and int(v) != v:
        fail(at, "expected integer")


def boolean(v, at):
    if type(v) is not bool:
        fail(at, "expected boolean")


def enum(v, at, values):
    if not isinstance(v, str) or v not in values:
        fail(at, f"invalid value {v!r}; expected {sorted(values)}")


def array(v, at, length=None, minimum=0):
    if (
        not isinstance(v, list)
        or len(v) < minimum
        or length is not None
        and len(v) != length
    ):
        fail(at, f"expected array (length={length}, minimum={minimum})")


def vector(v, at, length, **kwargs):
    array(v, at, length)
    for i, x in enumerate(v):
        number(x, f"{at}[{i}]", **kwargs)


def fields(v, at, rules):
    for key, rule in rules.items():
        if key in v:
            rule(v[key], f"{at}.{key}")


def safe_path(root, value, at, check_files=True):
    string(value, at, True)
    normalized = value.replace("\\", "/")
    if (
        normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or ".." in normalized.split("/")
        or "\0" in value
    ):
        fail(at, "path must be relative and must not escape the project")
    if root is not None:
        resolved = (Path(root) / normalized).resolve()
        if not resolved.is_relative_to(Path(root).resolve()):
            fail(at, "path resolves outside project (including symlinks)")
        if check_files and not resolved.is_file():
            fail(at, f"file does not exist: {value}")
        return resolved
    return Path(normalized)


H_ALIGN = {"left", "center", "right", "justify", "distributed"}
TEXT_STYLE = set(
    "color fontSize fontFamily bold italic backgroundColor lineHeight lineHeightPx letterSpacing marginTop".split()
)
TABLE_STYLE = set(
    "cellStyle firstRowStyle lastRowStyle firstColumnStyle lastColumnStyle bodyStyles rowOverColumn".split()
)
TRANSFORMS = {"rotation", "opacity", "flip"}
BASE = {"elementId", "elementType", "bounds"}
SHAPE = {"shapeName", "adjustments", "viewBox", "path"}
DECORATION = {"fill", "border", "shadow"}
FORMATS = {"0", "0.0", "0%", "0.0%", "#,##0", "0.0E+00"}
EFFECTS = set(
    "appear fade-in fly-in zoom-in wipe-in float-in peek-in rise-in pulse grow-shrink spin teeter fill-color transparency color-pulse disappear fade-out fly-out zoom-out wipe-out float-out motion-path".split()
)
CHART_TYPES = {"bar", "line", "area", "scatter", "bubble", "pie", "radar", "waterfall"}


class Validator:
    def __init__(self, manifest, root=None, check_files=True):
        self.root, self.check_files = root, check_files
        theme = manifest.get("theme", {}) if isinstance(manifest, dict) else {}
        self.theme = theme if isinstance(theme, dict) else {}
        self.shapes = set(
            Path(__file__).with_name("shape_names.txt").read_text().split()
        )

    def color(self, v, at):
        string(v, at)
        if re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", v):
            return
        if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_-]*", v) and v[1:] in self.theme.get(
            "colors", {}
        ):
            return
        fail(at, "expected HEX6/HEX8 or known $theme color")

    def reference(self, v, at, group):
        string(v, at, True)
        if not re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_-]*", v) or v[
            1:
        ] not in self.theme.get(group, {}):
            fail(at, f"unknown {group} reference; use $key")

    def font(self, v, at):
        if isinstance(v, str):
            string(v, at, True)
        else:
            obj(v, at, {"latin", "ea"}, {"latin", "ea"})
            for k in v:
                string(v[k], at + "." + k, True)

    def align(self, v, at):
        array(v, at, 2)
        enum(v[0], at, H_ALIGN)
        enum(v[1], at, {"top", "middle", "bottom"})

    def border(self, v, at, arrow=False):
        obj(v, at, {"style", "width", "color"} | ({"arrow"} if arrow else set()))
        fields(
            v,
            at,
            {
                "style": lambda x, p: enum(x, p, {"solid", "dash", "dot"}),
                "width": lambda x, p: number(x, p, positive=True),
                "color": self.color,
            },
        )
        if "arrow" in v and type(v["arrow"]) is not bool:
            enum(v["arrow"], at + ".arrow", {"start", "end", "both"})

    def borders(self, v, at):
        if v is None:
            return
        if isinstance(v, list):
            if len(v) not in (2, 4):
                fail(at, "border array must have 2 or 4 entries")
            for item in v:
                if item is not None:
                    self.border(item, at)
        else:
            self.border(v, at)

    def shadow(self, v, at):
        obj(v, at, {"blur", "color", "offset"}, {"blur", "color"})
        number(v["blur"], at + ".blur", minimum=0)
        self.color(v["color"], at + ".color")
        if "offset" in v:
            vector(v["offset"], at + ".offset", 2)

    def gradient(self, v, at):
        obj(
            v,
            at,
            {"type", "gradientType", "stops", "angle"},
            {"type", "gradientType", "stops"},
        )
        enum(v["type"], at + ".type", {"gradient"})
        enum(v["gradientType"], at + ".gradientType", {"linear", "radial"})
        array(v["stops"], at + ".stops", minimum=2)
        previous = -1
        for i, stop in enumerate(v["stops"]):
            p = f"{at}.stops[{i}]"
            obj(stop, p, {"position", "color"}, {"position", "color"})
            number(stop["position"], p + ".position", minimum=0, maximum=1)
            if stop["position"] < previous:
                fail(p, "gradient positions must be non-decreasing")
            previous = stop["position"]
            self.color(stop["color"], p + ".color")
        if "angle" in v:
            number(
                v["angle"], at + ".angle", minimum=0, maximum=360, exclusive_max=True
            )

    def image_source(self, v, at):
        string(v, at, True)
        if re.match(r"(?i)^(https?://|data:[^,]+,)", v):
            return
        safe_path(self.root, v, at, self.check_files)

    def crop(self, v, at):
        obj(v, at, {"left", "right", "top", "bottom"})
        for k in v:
            number(v[k], at + "." + k)
        if (
            v.get("left", 0) + v.get("right", 0) >= 1
            or v.get("top", 0) + v.get("bottom", 0) >= 1
        ):
            fail(at, "crop sides must sum to less than 1")

    def fit(self, v, at):
        obj(v, at, {"mode"}, {"mode"})
        enum(v["mode"], at + ".mode", {"fill", "contain", "cover"})

    def fill(self, v, at):
        obj(
            v,
            at,
            {
                "type",
                "color",
                "src",
                "fit",
                "crop",
                "opacity",
                "gradientType",
                "stops",
                "angle",
            },
            {"type"},
        )
        kind = v["type"]
        if kind == "solid":
            obj(v, at, {"type", "color"}, {"color"})
            self.color(v["color"], at + ".color")
        elif kind == "gradient":
            self.gradient(v, at)
        elif kind == "image":
            obj(v, at, {"type", "src", "fit", "crop", "opacity"}, {"src"})
            fields(
                v,
                at,
                {
                    "src": self.image_source,
                    "fit": self.fit,
                    "crop": self.crop,
                    "opacity": lambda x, p: number(x, p, minimum=0, maximum=1),
                },
            )
        else:
            fail(at, "unsupported fill type")

    def series_fill(self, v, at, collection=False):
        if isinstance(v, str):
            self.color(v, at)
        elif isinstance(v, dict) and v.get("type") == "gradient":
            self.gradient(v, at)
        elif collection and isinstance(v, list) and v:
            for x in v:
                self.series_fill(x, at)
        else:
            fail(at, "series fill must be color or gradient")

    def style(self, v, at, cell=False, extra=False):
        if not extra:
            obj(v, at, TEXT_STYLE | ({"fill", "border", "align"} if cell else set()))
        fields(
            v,
            at,
            {
                "color": self.color,
                "backgroundColor": self.color,
                "fontFamily": self.font,
                "bold": boolean,
                "italic": boolean,
                "fontSize": lambda x, p: number(x, p, positive=True),
                "lineHeight": lambda x, p: number(x, p, positive=True),
                "lineHeightPx": lambda x, p: number(x, p, positive=True),
                "letterSpacing": number,
                "marginTop": number,
            },
        )
        if cell:
            fields(
                v, at, {"fill": self.fill, "border": self.borders, "align": self.align}
            )

    def rich_style(self, v, at, tag):
        allowed = {
            "p": set(
                "text-align line-height margin-top margin-left margin-right".split()
            ),
            "li": set(
                "text-align line-height letter-spacing margin-top margin-left list-style list-style-type list-style-position list-style-image".split()
            ),
            "span": set(
                "color font-size font-family background-color font-weight font-style text-decoration".split()
            ),
        }.get(tag, set())
        numeric = r"[-+]?(?:\d+\.?\d*|\.\d+)"
        for declaration in v.split(";"):
            if not declaration.strip():
                continue
            key, sep, value = declaration.partition(":")
            key, value = key.strip().lower(), value.strip()
            if not sep or key not in allowed or not value:
                fail(at, f"unsupported or invalid CSS declaration {declaration!r}")
            if key in {"color", "background-color"}:
                self.color(value, at)
            if (
                key == "font-size"
                or key.startswith("margin-")
                or key == "letter-spacing"
            ):
                if not re.fullmatch(numeric + "px", value):
                    fail(at, "expected px value")
                if key == "font-size" and float(value[:-2]) <= 0:
                    fail(at, "font size must be positive")
            if key == "line-height" and (
                not re.fullmatch(numeric + "(?:px)?", value)
                or float(value.removesuffix("px")) <= 0
            ):
                fail(at, "line height must be positive")
            if key == "font-weight" and not re.fullmatch(r"normal|bold|[1-9]00", value):
                fail(at, "invalid font weight")
            if key == "font-style":
                enum(value, at, {"normal", "italic", "oblique"})
            if key == "text-align":
                enum(value, at, H_ALIGN)

    def rich_text(self, v, at):
        string(v, at)
        stack = []
        cursor = 0
        for match in re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9]*)\b([^>]*)>", v):
            if "<" in v[cursor : match.start()] or ">" in v[cursor : match.start()]:
                fail(at, "raw < or > must be escaped")
            cursor = match.end()
            closing, tag, attrs = match.groups()
            tag = tag.lower()
            if tag not in {
                "p",
                "span",
                "strong",
                "em",
                "u",
                "s",
                "sup",
                "sub",
                "a",
                "ul",
                "ol",
                "li",
                "br",
            }:
                fail(at, f"unsupported rich-text tag <{tag}>")
            if closing:
                if not stack or stack.pop() != tag or attrs.strip():
                    fail(at, "mismatched closing tag")
                continue
            selfclosing = attrs.rstrip().endswith("/")
            rest = (
                attrs.strip().removesuffix("/").strip()
                if selfclosing
                else attrs.strip()
            )
            parsed = {}
            while rest:
                am = re.match(
                    r"""([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
                    rest,
                )
                if not am:
                    fail(at, "invalid tag attribute syntax")
                key = am[1]
                if key in parsed:
                    fail(at, "duplicate tag attribute")
                parsed[key] = am[2] if am[2] is not None else am[3]
                rest = rest[am.end() :].strip()
            allowed = (
                {"style"}
                if tag in {"p", "span", "li"}
                else {"href"}
                if tag == "a"
                else set()
            )
            obj(parsed, at, allowed, {"href"} if tag == "a" else ())
            if "style" in parsed:
                self.rich_style(parsed["style"], at, tag)
            if tag == "a" and not re.match(r"(?i)^(https?://|mailto:)", parsed["href"]):
                fail(at, "unsupported hyperlink scheme")
            if tag == "li" and not {"ul", "ol"}.intersection(stack):
                fail(at, "li must be inside ul or ol")
            if tag in {"ul", "ol"} and stack and stack[-1] in {"ul", "ol"}:
                fail(at, "nested list must be inside li")
            if not selfclosing and tag != "br":
                stack.append(tag)
        if stack or "<" in v[cursor:] or ">" in v[cursor:]:
            fail(at, "unclosed tag or unescaped angle bracket")
        for formula in re.findall(r"\\\((.*?)\\\)", v, re.S):
            if "<" in formula or ">" in formula:
                fail(at, "rich tags inside formula")

    def content(self, v, at):
        obj(
            v,
            at,
            TEXT_STYLE
            | {"text", "style", "textDirection", "wrap", "align", "gradient", "shadow"},
            {"text"},
        )
        self.rich_text(v["text"], at + ".text")
        self.style(v, at, extra=True)
        fields(
            v,
            at,
            {
                "style": lambda x, p: self.reference(x, p, "textStyles"),
                "textDirection": lambda x, p: enum(x, p, {"horizontal", "vertical"}),
                "wrap": boolean,
                "align": self.align,
                "gradient": self.gradient,
                "shadow": self.shadow,
            },
        )

    def svg_path(self, v, at, motion=False):
        string(v, at, True)
        pattern = r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
        if re.sub(pattern, "", v).strip(" \t\r\n,"):
            fail(at, "invalid SVG path token")
        tokens = re.findall(pattern, v)
        counts = {
            "M": 2,
            "L": 2,
            "H": 1,
            "V": 1,
            "C": 6,
            "S": 4,
            "Q": 4,
            "T": 2,
            "A": 7,
            "Z": 0,
        }
        moves = 0
        i = 0
        while i < len(tokens):
            cmd = tokens[i].upper()
            if cmd not in counts:
                fail(at, "SVG segment must start with command")
            i += 1
            moves += cmd == "M"
            count = 0
            while i < len(tokens) and tokens[i].upper() not in counts:
                number(float(tokens[i]), at)
                count += 1
                i += 1
            if counts[cmd] == 0:
                if count:
                    fail(at, "Z cannot have coordinates")
            elif not count or count % counts[cmd]:
                fail(at, f"SVG {cmd} requires groups of {counts[cmd]} numbers")
        if not moves:
            fail(at, "SVG requires move command")
        if motion and (
            moves != 1
            or not re.match(
                r"\s*M\s*[-+]?0(?:\.0*)?\s*[, ]\s*[-+]?0(?:\.0*)?(?=\s|,|[LlQqCc]|$)",
                v,
                re.I,
            )
            or re.search(r"[AaTtHhVvSsZz]", v)
        ):
            fail(at, "motion-path must start with M 0 0; supports one M/L/Q/C subpath")

    def shape(self, v, at, decorated=False):
        obj(v, at, SHAPE | (DECORATION if decorated else set()), {"shapeName"})
        enum(v["shapeName"], at + ".shapeName", self.shapes)
        if "adjustments" in v:
            array(v["adjustments"], at)
            for x in v["adjustments"]:
                number(x, at)
        if v["shapeName"] == "custom":
            obj(v, at, set(v), {"viewBox", "path"})
            vector(v["viewBox"], at + ".viewBox", 2, positive=True)
            self.svg_path(v["path"], at + ".path")
        elif "path" in v or "viewBox" in v:
            fail(at, "path/viewBox only valid for custom shapes")
        if decorated:
            fields(
                v, at, {"fill": self.fill, "border": self.border, "shadow": self.shadow}
            )

    def table_style(self, v, at):
        obj(v, at, TABLE_STYLE)
        for key, x in v.items():
            if key == "rowOverColumn":
                boolean(x, at + "." + key)
            elif key == "bodyStyles":
                array(x, at + "." + key)
                for item in x:
                    self.style(item, at + "." + key, cell=True)
            else:
                self.style(x, at + "." + key, cell=True)

    def table(self, v, at):
        obj(
            v,
            at,
            BASE | {"columnWidths", "rowHeights", "rows", "style", "fill", "shadow"},
            {"columnWidths", "rowHeights", "rows"},
        )
        for key in ("columnWidths", "rowHeights"):
            array(v[key], at + "." + key, minimum=1)
            for x in v[key]:
                number(x, at + "." + key, positive=True, maximum=1)
            if abs(sum(v[key]) - 1) > 1e-6:
                fail(at + "." + key, "must sum to 1")
        nr, nc = len(v["rowHeights"]), len(v["columnWidths"])
        array(v["rows"], at + ".rows", nr)
        occupied = set()
        for r, row in enumerate(v["rows"]):
            array(row, at + ".rows")
            c = 0
            for i, cell in enumerate(row):
                while (r, c) in occupied:
                    c += 1
                p = f"{at}.rows[{r}][{i}]"
                obj(
                    cell,
                    p,
                    TEXT_STYLE
                    | {
                        "text",
                        "textStyle",
                        "fill",
                        "border",
                        "align",
                        "rowSpan",
                        "colSpan",
                    },
                )
                self.style(cell, p, cell=True, extra=True)
                fields(
                    cell,
                    p,
                    {
                        "text": self.rich_text,
                        "textStyle": lambda x, p: self.reference(x, p, "textStyles"),
                    },
                )
                rs, cs = cell.get("rowSpan", 1), cell.get("colSpan", 1)
                number(rs, p + ".rowSpan", minimum=1, integer=True)
                number(cs, p + ".colSpan", minimum=1, integer=True)
                if r + rs > nr or c + cs > nc:
                    fail(p, "merge exceeds table dimensions")
                for rr in range(r, r + int(rs)):
                    for cc in range(c, c + int(cs)):
                        if (rr, cc) in occupied:
                            fail(p, "merge overlaps another cell")
                        occupied.add((rr, cc))
                c += int(cs)
        if len(occupied) != nr * nc:
            fail(at, "table is missing unmerged cells")
        if "style" in v:
            if isinstance(v["style"], str):
                self.reference(v["style"], at + ".style", "tableStyles")
            else:
                self.table_style(v["style"], at + ".style")
        fields(v, at, {"fill": self.fill, "shadow": self.shadow})

    def element(self, v, at):
        obj(v, at, set(v) if isinstance(v, dict) else (), BASE)
        string(v["elementId"], at + ".elementId", True)
        kind = v["elementType"]
        enum(
            kind,
            at + ".elementType",
            {"text", "shape", "line", "image", "icon", "table", "chart"},
        )
        vector(v["bounds"], at + ".bounds", 4)
        w, h = v["bounds"][2:]
        if w < 0 or h < 0 or (w == 0 or h == 0) and kind != "line" or w == h == 0:
            fail(at + ".bounds", "invalid width/height")
        if kind == "text":
            obj(v, at, BASE | {"content"}, {"content"})
            self.content(v["content"], at + ".content")
            return
        if kind == "table":
            self.table(v, at)
            return
        if kind == "chart":
            self.chart(v, at)
            return
        allowed = {
            "shape": SHAPE | DECORATION,
            "line": {"viewBox", "points", "curve", "arrow", "border", "shadow"},
            "image": {"src", "cropShape", "fit", "crop", "border", "shadow"},
            "icon": {"iconName"} | DECORATION,
        }[kind]
        obj(v, at, BASE | TRANSFORMS | allowed)
        fields(
            v,
            at,
            {
                "rotation": number,
                "opacity": lambda x, p: number(x, p, minimum=0, maximum=1),
            },
        )
        if "flip" in v:
            array(v["flip"], at + ".flip", 2)
            for x in v["flip"]:
                boolean(x, at + ".flip")
        fields(v, at, {"fill": self.fill, "border": self.border, "shadow": self.shadow})
        if kind == "shape":
            self.shape(
                {k: x for k, x in v.items() if k in SHAPE | DECORATION}, at, True
            )
        elif kind == "image":
            obj(v, at, set(v), {"src"})
            fields(
                v,
                at,
                {
                    "src": self.image_source,
                    "cropShape": self.shape,
                    "fit": self.fit,
                    "crop": self.crop,
                },
            )
        elif kind == "icon":
            string(v.get("iconName"), at + ".iconName", True)
            if not re.fullmatch(r"(fas|far|fab):[^:]+", v["iconName"]):
                fail(at, "iconName must use fas:name, far:name, or fab:name")
        elif kind == "line":
            obj(v, at, set(v), {"viewBox", "points"})
            vector(v["viewBox"], at + ".viewBox", 2, positive=True)
            string(v["points"], at + ".points")
            pieces = v["points"].split()
            if len(pieces) < 2:
                fail(at, "line requires at least two points")
            for piece in pieces:
                pair = piece.split(",")
                try:
                    xy = [float(x) for x in pair]
                except ValueError:
                    fail(at, "invalid point")
                vector(xy, at + ".points", 2, minimum=0)
                if any(x > limit for x, limit in zip(xy, v["viewBox"])):
                    fail(at, "line point outside viewBox")
            if "curve" in v:
                enum(v["curve"], at + ".curve", {"sharp", "round", "smooth"})
            if "arrow" in v:
                array(v["arrow"], at + ".arrow", 2)
                for x in v["arrow"]:
                    if x is not None:
                        enum(x, at + ".arrow", {"arrow", "stealth", "diamond", "oval"})

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

    def animation(self, v, at, ids):
        obj(
            v,
            at,
            {
                "elementId",
                "effect",
                "trigger",
                "direction",
                "durationMs",
                "delayMs",
                "easing",
                "repeat",
                "path",
                "color",
                "amount",
            },
            {"elementId", "effect"},
        )
        string(v["elementId"], at + ".elementId", True)
        if v["elementId"] not in ids:
            fail(at, "animation target does not exist")
        enum(v["effect"], at + ".effect", EFFECTS)
        fields(
            v,
            at,
            {
                "trigger": lambda x, p: enum(
                    x, p, {"onClick", "withPrevious", "afterPrevious"}
                ),
                "direction": lambda x, p: enum(x, p, {"up", "down", "left", "right"}),
                "durationMs": lambda x, p: number(x, p, positive=True),
                "delayMs": lambda x, p: number(x, p, minimum=0),
                "repeat": lambda x, p: number(x, p, minimum=1, integer=True),
                "easing": lambda x, p: enum(
                    x, p, {"linear", "ease-in", "ease-out", "ease-in-out"}
                ),
            },
        )
        effect = v["effect"]
        if effect in {"float-in", "float-out"} and v.get("direction", "up") not in {
            "up",
            "down",
        }:
            fail(at, "float effects support only up/down")
        for key, needed in {
            "path": effect == "motion-path",
            "color": effect in {"fill-color", "color-pulse"},
            "amount": effect == "transparency",
        }.items():
            if needed and key not in v:
                fail(at, f'missing required field "{key}"')
            if not needed and key in v:
                fail(at, key + " is only valid for its corresponding effect")
        if "path" in v:
            self.svg_path(v["path"], at + ".path", True)
        if "color" in v:
            string(v["color"], at + ".color")
            if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", v["color"]):
                fail(at, "animation color must be six hex digits")
        if "amount" in v:
            number(v["amount"], at + ".amount", minimum=0, maximum=1)

    def page(self, v, at):
        obj(
            v,
            at,
            {"pageType", "background", "notes", "elements", "animations", "allowedOverlaps"},
            {"elements"},
        )
        fields(
            v,
            at,
            {
                "pageType": lambda x, p: string(x, p, True),
                "background": self.fill,
                "notes": string,
            },
        )
        array(v["elements"], at + ".elements")
        ids = set()
        for i, e in enumerate(v["elements"]):
            self.element(e, f"{at}.elements[{i}]")
            if e["elementId"] in ids:
                fail(at, "duplicate elementId")
            ids.add(e["elementId"])
        from .occupancy import overlap_declarations
        overlap_declarations(v)
        if "animations" in v:
            array(v["animations"], at + ".animations")
            for i, a in enumerate(v["animations"]):
                self.animation(a, f"{at}.animations[{i}]", ids)


def validate_project(manifest, pages, root=None, check_files=True):
    """Validate raw manifest + page objects before normalization or resource IO."""
    obj(
        manifest,
        "manifest",
        {"version", "title", "customFonts", "size", "theme", "pages"},
        {"version", "size", "pages"},
    )
    enum(manifest["version"], "manifest.version", {"v2"})
    vector(manifest["size"], "manifest.size", 2, positive=True)
    array(manifest["pages"], "manifest.pages", minimum=1)
    array(pages, "pages", len(manifest["pages"]))
    seen = set()
    for p in manifest["pages"]:
        safe_path(root, p, "manifest.pages", check_files)
        if p in seen:
            fail("manifest.pages", "duplicate page path")
        seen.add(p)
    v = Validator(manifest, root, check_files)
    if "title" in manifest:
        string(manifest["title"], "manifest.title")
    if "customFonts" in manifest:
        array(manifest["customFonts"], "manifest.customFonts")
        for font in manifest["customFonts"]:
            obj(font, "customFonts", {"family", "src"}, {"family", "src"})
            for k in font:
                string(font[k], "customFonts." + k, True)
    if "theme" in manifest:
        obj(manifest["theme"], "theme", {"colors", "textStyles", "tableStyles"})
        for group, values in manifest["theme"].items():
            if not isinstance(values, dict):
                fail("theme." + group, "expected map")
            for key, value in values.items():
                string(key, "theme." + group, True)
                {
                    "colors": v.color,
                    "textStyles": v.style,
                    "tableStyles": v.table_style,
                }[group](value, "theme." + group + "." + key)
    for i, page in enumerate(pages):
        v.page(page, f"pages[{i}]({manifest['pages'][i]})")
    return {"ok": True, "pageCount": len(pages)}
