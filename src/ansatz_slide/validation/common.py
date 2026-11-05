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
    """解析相对源目录的路径，并拒绝路径穿越或符号链接逃逸。"""
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


class StyleValidator:
    """共享值、样式与素材校验；元素校验复用同一语义契约。"""

    def __init__(self, manifest, root=None, check_files=True):
        self.root, self.check_files = root, check_files
        theme = manifest.get("theme", {}) if isinstance(manifest, dict) else {}
        self.theme = theme if isinstance(theme, dict) else {}
        self.shapes = set(
            (Path(__file__).resolve().parents[1] / "shape_names.txt")
            .read_text()
            .split()
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
