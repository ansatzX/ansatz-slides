"""文字、形状和表格元素校验。"""

import re

from .common import (
    BASE,
    DECORATION,
    H_ALIGN,
    SHAPE,
    TABLE_STYLE,
    TEXT_STYLE,
    TRANSFORMS,
    array,
    boolean,
    enum,
    fail,
    fields,
    number,
    obj,
    string,
    vector,
)


class ContentValidator:
    def rich_style(self, v, at, tag):
        allowed = {
            "p": set(
                "text-align line-height margin-top margin-left margin-right".split()
            ),
            "li": set(
                "text-align line-height letter-spacing margin-top margin-left".split()
            ),
            "span": set(
                "color font-size font-family background-color font-weight font-style text-decoration letter-spacing".split()
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
            if key == "text-decoration" and (
                not set(value.split()) <= {"none", "underline", "line-through"}
                or ("none" in value.split() and value != "none")
            ):
                fail(at, "supported text-decoration: none, underline, line-through")

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
