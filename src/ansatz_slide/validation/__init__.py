"""严格 DSL 校验入口，组合共享样式、内容元素和图表规则。"""

import re

from .charts import ChartValidator
from .common import (
    BASE,
    CHART_TYPES,
    DECORATION,
    EFFECTS,
    FORMATS,
    H_ALIGN,
    SHAPE,
    TABLE_STYLE,
    TEXT_STYLE,
    TRANSFORMS,
    StyleValidator,
    ValidationError,
    array,
    boolean,
    enum,
    fail,
    fields,
    finite,
    number,
    obj,
    safe_path,
    string,
    vector,
)
from .content import ContentValidator


class Validator(StyleValidator, ContentValidator, ChartValidator):
    """按同一上下文校验整个项目；未知字段和不支持的语义均拒绝。"""

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
            {
                "pageType",
                "background",
                "notes",
                "elements",
                "animations",
                "allowedOverlaps",
            },
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
        from ..occupancy import overlap_declarations

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


__all__ = [
    "BASE",
    "CHART_TYPES",
    "ChartValidator",
    "ContentValidator",
    "DECORATION",
    "EFFECTS",
    "FORMATS",
    "H_ALIGN",
    "SHAPE",
    "StyleValidator",
    "TABLE_STYLE",
    "TEXT_STYLE",
    "TRANSFORMS",
    "ValidationError",
    "Validator",
    "array",
    "boolean",
    "enum",
    "fail",
    "fields",
    "finite",
    "number",
    "obj",
    "safe_path",
    "string",
    "validate_project",
    "vector",
]
