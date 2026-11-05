"""HTML-like pptx.yaml rich text → explicit paragraphs and DrawingML runs.

此解析器实现项目支持的富文本子集，不是浏览器排版引擎，不能据此推断未支持
的 HTML 语义。导出路径启用原生公式时，公式标记会交给独立的 Office Math 序列化器。
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from .styles import color_xml, fill_xml, shadow_xml
from .xml import emu, round_half_away, tag, text


@dataclass
class Run:
    value: str
    style: dict = field(default_factory=dict)
    kind: str = "text"


@dataclass
class Paragraph:
    runs: list = field(default_factory=list)
    style: dict = field(default_factory=dict)


CSS_NAMES = {
    "font-family": "fontFamily",
    "font-size": "fontSize",
    "color": "color",
    "font-weight": "bold",
    "font-style": "italic",
    "text-decoration": "decoration",
    "text-align": "align",
    "line-height": "lineHeight",
    "margin-top": "marginTop",
    "margin-left": "marginLeft",
    "margin-right": "marginRight",
    "letter-spacing": "letterSpacing",
    "background-color": "inlineHighlight",
}


def css_style(value):
    out = {}
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        key, val = map(str.strip, declaration.split(":", 1))
        key = CSS_NAMES.get(key.lower())
        if not key:
            continue
        if key == "bold":
            val = val == "bold" or (val.isdigit() and int(val) >= 600)
        elif key == "italic":
            val = val in ("italic", "oblique")
        elif key in [
            "fontSize",
            "letterSpacing",
            "marginTop",
            "marginLeft",
            "marginRight",
        ]:
            try:
                val = float(val.removesuffix("px").removesuffix("pt"))
            except ValueError:
                continue
        elif key == "fontFamily":
            val = val.strip("'\"")
        elif key == "lineHeight":
            try:
                if val.endswith("px"):
                    key = "lineHeightPx"
                    val = float(val[:-2])
                else:
                    val = float(val)
            except ValueError:
                continue
        out[key] = val
    return out


class RichTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragraphs = []
        self.current = None
        self.stack = [{}]
        self.tags = []

    def ensure_paragraph(self):
        if self.current is None:
            self.current = Paragraph()
            self.paragraphs.append(self.current)

    def handle_starttag(self, name, attrs):
        attrs = dict(attrs)
        if name in ["p", "li"]:
            self.current = Paragraph(style=css_style(attrs.get("style", "")))
            self.paragraphs.append(self.current)
            if name == "li":
                self.current.style.update(
                    {
                        "bullet": "number"
                        if next(
                            (t for t in reversed(self.tags) if t in ["ol", "ul"]), None
                        )
                        == "ol"
                        else "bullet",
                        "marginTop": self.current.style.get("marginTop", 0.1),
                        "level": max(0, sum(t in ["ol", "ul"] for t in self.tags) - 1),
                    }
                )
        elif name == "br":
            self.ensure_paragraph()
            self.current.runs.append(Run("", dict(self.stack[-1]), "break"))
            return
        style = {**self.stack[-1], **css_style(attrs.get("style", ""))}
        if name == "strong":
            style["bold"] = True
        if name == "em":
            style["italic"] = True
        if name == "u":
            style["underline"] = True
        if name == "s":
            style["strike"] = True
        if name in ["sup", "sub"]:
            style["baseline"] = 30000 if name == "sup" else -25000
        if name == "a":
            style.update(
                {"href": attrs.get("href"), "underline": True, "color": "#0563C1"}
            )
        self.stack.append(style)
        self.tags.append(name)

    def handle_endtag(self, name):
        if name in self.tags:
            index = len(self.tags) - 1 - self.tags[::-1].index(name)
            self.stack = self.stack[: index + 1]
            self.tags = self.tags[:index]
        if name in ["p", "li"]:
            self.current = None

    def handle_data(self, value):
        if not value or (self.current is None and not value.strip()):
            return
        self.ensure_paragraph()
        if (
            self.current.runs
            and self.current.runs[-1].kind == "text"
            and self.current.runs[-1].style == self.stack[-1]
        ):
            self.current.runs[-1].value += value
        else:
            self.current.runs.append(Run(value, dict(self.stack[-1])))


def run_properties(style, theme=None):
    attrs = {
        "lang": "en-US",
        "sz": round_half_away(style.get("fontSize", 18) * 100),
        "noProof": "1",
    }
    for key, attr in [("bold", "b"), ("italic", "i")]:
        if style.get(key):
            attrs[attr] = "1"
    if style.get("underline") or "underline" in style.get("decoration", "").split():
        attrs["u"] = "sng"
    if style.get("strike") or "line-through" in style.get("decoration", "").split():
        attrs["strike"] = "sngStrike"
    if style.get("baseline"):
        attrs["baseline"] = style["baseline"]
    if style.get("letterSpacing"):
        attrs["spc"] = round_half_away(style["letterSpacing"] * 100)
        attrs["kern"] = 0
    font = style.get("fontFamily", "Times New Roman")
    fonts = font if isinstance(font, dict) else {"latin": font, "ea": font}
    content = (
        fill_xml(style["gradient"], theme)
        if style.get("gradient")
        else tag(
            "a:solidFill", children=color_xml(style.get("color", "#000000"), theme)
        )
    )
    content += shadow_xml(style.get("shadow"), theme)
    if style.get("inlineHighlight"):
        content += tag(
            "a:highlight", children=color_xml(style["inlineHighlight"], theme)
        )
    content += tag(
        "a:latin", {"typeface": fonts.get("latin", "Times New Roman")}
    ) + tag(
        "a:ea", {"typeface": fonts.get("ea", fonts.get("latin", "Times New Roman"))}
    )
    if style.get("hyperlinkId"):
        content += tag("a:hlinkClick", {"r:id": style["hyperlinkId"]})
    return tag("a:rPr", attrs, content)


def paragraphs_xml(
    html, base, theme=None, cell=False, align=None, relationships=None, native_math=True
):
    parser = RichTextParser()
    parser.feed(str(html))
    parser.close()
    paragraphs = parser.paragraphs or [Paragraph()]
    result = []
    for para in paragraphs:
        style = {**base, **para.style}
        if "lineHeight" in para.style and "lineHeightPx" not in para.style:
            style.pop("lineHeightPx", None)
        properties = {}
        for key, attr in (("marginLeft", "marL"), ("marginRight", "marR")):
            if key in style:
                properties[attr] = emu(style[key])
        alignment = style.get("align", align)
        if isinstance(alignment, list):
            alignment = alignment[0]
        if style.get("level"):
            properties["lvl"] = style["level"]
        if alignment:
            properties["algn"] = {
                "left": "l",
                "center": "ctr",
                "right": "r",
                "justify": "just",
                "distributed": "dist",
            }.get(alignment, alignment)
        spacing = ""
        if not cell or "lineHeight" in para.style or "lineHeightPx" in para.style:
            spacing = tag(
                "a:lnSpc",
                children=tag(
                    "a:spcPts", {"val": round_half_away(style["lineHeightPx"] * 100)}
                )
                if "lineHeightPx" in style
                else tag(
                    "a:spcPct",
                    {"val": round_half_away(style.get("lineHeight", 1.2) * 100000)},
                ),
            )
        if style.get("marginTop"):
            spacing += tag(
                "a:spcBef",
                children=tag(
                    "a:spcPts", {"val": round_half_away(style["marginTop"] * 100)}
                ),
            )
        if style.get("bullet"):
            spacing += (
                tag("a:buAutoNum", {"type": "arabicPeriod"})
                if style["bullet"] == "number"
                else tag("a:buChar", {"char": "•"})
            )
        content = tag("a:pPr", properties, spacing)
        for run in para.runs:
            runstyle = {**style, **run.style}
            if run.kind == "break":
                content += tag("a:br", children=run_properties(runstyle, theme))
                continue
            if runstyle.get("href") and relationships:
                runstyle["hyperlinkId"] = relationships.add(
                    "hyperlink", runstyle["href"], external=True
                )
            fragments = (
                re.split(r"(\\\(.*?\\\))", run.value, flags=re.S)
                if native_math
                else [run.value]
            )
            for fragment in fragments:
                if not fragment:
                    continue
                if (
                    native_math
                    and fragment.startswith("\\(")
                    and fragment.endswith("\\)")
                ):
                    from .mathtext import math_xml

                    content += math_xml(fragment[2:-2], runstyle, theme)
                else:
                    content += tag(
                        "a:r",
                        children=run_properties(runstyle, theme)
                        + text("a:t", fragment),
                    )
        if (
            native_math
            and para.runs
            and not re.sub(
                r"\\\(.*?\\\)", "", "".join(run.value for run in para.runs), flags=re.S
            )
        ):
            content += tag(
                "a:r",
                children=tag(
                    "a:rPr",
                    {
                        "lang": "en-US",
                        "sz": round_half_away(style.get("fontSize", 16) * 100),
                        "noProof": 1,
                    },
                )
                + text("a:t", " ", {"xml:space": "preserve"}),
            )
        if not cell:
            content += tag(
                "a:endParaRPr",
                {
                    "lang": "en-US",
                    "sz": round_half_away(style.get("fontSize", 18) * 100),
                    "noProof": "1",
                },
            )
        result.append(tag("a:p", children=content))
    return "".join(result)


def text_body(content, theme=None, relationships=None, native_math=True):
    content = content or {}
    base = {
        "fontSize": 16,
        "fontFamily": "MiSans",
        "color": "#333333",
        **(theme or {})
        .get("textStyles", {})
        .get((content.get("style") or "").lstrip("$"), {}),
        **content,
    }
    attrs = {
        "lIns": "0",
        "rIns": "0",
        "tIns": "0",
        "bIns": "0",
        "wrap": "square",
        "rtlCol": "0",
    }
    if content.get("wrap") is False:
        attrs["wrap"] = "none"
    if content.get("textDirection") == "vertical":
        attrs["vert"] = "eaVert"
    alignment = content.get("align")
    if isinstance(alignment, list) and len(alignment) > 1:
        attrs["anchor"] = {"top": "t", "middle": "ctr", "bottom": "b"}.get(
            alignment[1], "t"
        )
    return tag(
        "p:txBody",
        children=tag("a:bodyPr", attrs)
        + tag("a:lstStyle")
        + paragraphs_xml(
            content.get("text", ""),
            base,
            theme,
            align=alignment,
            relationships=relationships,
            native_math=native_math,
        ),
    )
