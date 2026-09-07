"""Small, readable LaTeX tokenizer and Office Math serializer.

Preserves the bundled writer's supported grammar: groups, fractions, scripts,
symbols and font commands. Unknown commands remain literal text, as in the
original writer; this is deliberately not a claim of full TeX support.
"""

import re

from .styles import fill_xml
from .xml import tag, text

SYMBOLS = dict(
    zip(
        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega".split(),
        "αβγδεζηθικλμνξοπρστυφχψω",
    )
)
SYMBOLS.update(
    dict(
        zip(
            "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split(),
            "ΓΔΘΛΞΠΣΥΦΨΩ",
        )
    )
)
SYMBOLS.update(
    {
        "sum": "∑",
        "prod": "∏",
        "int": "∫",
        "infty": "∞",
        "leq": "≤",
        "geq": "≥",
        "neq": "≠",
        "times": "×",
        "cdot": "⋅",
        "pm": "±",
        "mp": "∓",
        "approx": "≈",
        "equiv": "≡",
        "to": "→",
        "rightarrow": "→",
        "leftarrow": "←",
        "partial": "∂",
        "nabla": "∇",
        "in": "∈",
        "notin": "∉",
        "subset": "⊂",
        "subseteq": "⊆",
        "cup": "∪",
        "cap": "∩",
        "forall": "∀",
        "exists": "∃",
        "ldots": "…",
        "cdots": "⋯",
        "langle": "⟨",
        "rangle": "⟩",
        "vert": "|",
        "Vert": "‖",
    }
)


class MathParser:
    def __init__(self, source, style, theme):
        self.tokens = re.findall(r"\\[a-zA-Z]+|\\.|[^\s]", source)
        self.index = 0
        self.style = style
        self.theme = theme

    def properties(self, italic=None, bold=None):
        attrs = {"lang": "en-US", "noProof": 1}
        if bold:
            attrs["b"] = 1
        if italic is not None:
            attrs["i"] = int(italic)
        font = self.style.get("fontFamily", "MiSans")
        if isinstance(font, dict):
            font = font.get("latin", "MiSans")
        return tag(
            "a:rPr",
            attrs,
            fill_xml(self.style.get("color", "#333333"), self.theme)
            + tag("a:latin", {"typeface": font}),
        )

    def run(self, value, mode=None):
        italic = (
            len(value) == 1 and value.isascii() and value.isalpha()
            if mode is None
            else mode == "mathit"
        )
        return tag(
            "m:r",
            children=self.properties(italic, mode == "mathbf") + text("m:t", value),
        )

    def atom(self, mode=None):
        if self.index >= len(self.tokens):
            return ""
        token = self.tokens[self.index]
        self.index += 1
        if token == "{":
            result = self.sequence(mode, True)
            if self.index < len(self.tokens) and self.tokens[self.index] == "}":
                self.index += 1
            return result
        if token in ["\\frac", "\\dfrac", "\\tfrac"]:
            numerator = self.atom(mode)
            denominator = self.atom(mode)
            return tag(
                "m:f",
                children=tag("m:fPr", children=tag("m:type", {"m:val": "bar"}))
                + tag("m:num", children=numerator)
                + tag("m:den", children=denominator),
            )
        if token in ["\\mathbf", "\\mathrm", "\\mathit", "\\text", "\\operatorname"]:
            return self.atom(token[1:])
        if token in ["\\left", "\\right"]:
            return self.atom(mode)
        if token in ["\\,", "\\;", "\\:", "\\ ", "\\quad", "\\qquad"]:
            return self.run(" ", mode)
        if token == "\\!":
            return ""
        if token.startswith("\\"):
            value = SYMBOLS.get(token[1:], token)
            if token in ["\\{", "\\}", "\\_", "\\%", "\\#", "\\&", "\\$", "\\\\"]:
                value = token[1:]
            return self.run(value, "mathrm" if mode is None else mode)
        return self.run(token, mode)

    def sequence(self, mode=None, grouped=False):
        output = []
        while self.index < len(self.tokens):
            if self.tokens[self.index] == "}" and grouped:
                break
            base = self.atom(mode)
            sub = sup = None
            while self.index < len(self.tokens) and self.tokens[self.index] in [
                "_",
                "^",
            ]:
                marker = self.tokens[self.index]
                self.index += 1
                script = self.atom(mode)
                if marker == "_":
                    sub = script
                else:
                    sup = script
            if sub is not None or sup is not None:
                kind = (
                    "sSubSup"
                    if sub is not None and sup is not None
                    else "sSub"
                    if sub is not None
                    else "sSup"
                )
                content = tag(
                    "m:" + kind + "Pr",
                    children=tag("m:ctrlPr", children=self.properties()),
                ) + tag("m:e", children=base)
                if sub is not None:
                    content += tag("m:sub", children=sub)
                if sup is not None:
                    content += tag("m:sup", children=sup)
                base = tag("m:" + kind, children=content)
            output.append(base)
        return "".join(output)


def math_xml(source, style, theme):
    return tag(
        "a14:m",
        children=tag("m:oMath", children=MathParser(source, style, theme).sequence()),
    )
