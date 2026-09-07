"""PowerPoint timing trees from declarative pptx.yaml animation effects.

Timing nodes have package-local integer IDs. Behaviors target slide shape IDs;
click groups contain parallel effects, while afterPrevious starts a new stage.
"""

import re

from .styles import color_xml
from .xml import round_half_away, tag, text

PRESETS = {
    "appear": (1, "entr"),
    "fade-in": (10, "entr"),
    "fly-in": (2, "entr"),
    "zoom-in": (23, "entr"),
    "wipe-in": (22, "entr"),
    "float-in": (30, "entr"),
    "peek-in": (12, "entr"),
    "rise-in": (34, "entr"),
    "pulse": (26, "emph"),
    "grow-shrink": (6, "emph"),
    "spin": (8, "emph"),
    "teeter": (32, "emph"),
    "fill-color": (1, "emph"),
    "transparency": (9, "emph"),
    "color-pulse": (0, "emph"),
    "disappear": (1, "exit"),
    "fade-out": (10, "exit"),
    "fly-out": (2, "exit"),
    "zoom-out": (23, "exit"),
    "wipe-out": (22, "exit"),
    "float-out": (30, "exit"),
    "motion-path": (0, "path"),
}


def condition(delay):
    return tag("p:stCondLst", children=tag("p:cond", {"delay": delay}))


def children(body):
    return tag("p:childTnLst", children=body)


class TimingWriter:
    def __init__(self, shape_ids, size, theme, elements=()):
        self.elements = {e["elementId"]: e for e in elements}
        self.next_id = 3
        self.shape_ids, self.size, self.theme = shape_ids, size, theme

    def allocate(self):
        result = self.next_id
        self.next_id += 1
        return result

    def behavior(
        self,
        shape_id,
        duration,
        attributes=(),
        hold=True,
        delay=None,
        additive=False,
        **timing,
    ):
        attrs = {"id": self.allocate(), "dur": round_half_away(duration), **timing}
        if hold:
            attrs["fill"] = "hold"
        body = tag("p:cTn", attrs, condition(delay) if delay is not None else "")
        body += tag("p:tgtEl", children=tag("p:spTgt", {"spid": shape_id}))
        if attributes:
            body += tag(
                "p:attrNameLst",
                children="".join(text("p:attrName", name) for name in attributes),
            )
        return tag("p:cBhvr", {"additive": "base"} if additive else {}, body)

    def visibility(self, shape_id, visible, delay=0):
        return tag(
            "p:set",
            children=self.behavior(shape_id, 1, ["style.visibility"], delay=delay)
            + tag(
                "p:to",
                children=tag("p:strVal", {"val": "visible" if visible else "hidden"}),
            ),
        )

    def interpolate(self, shape_id, duration, property_name, start, end):
        body = self.behavior(shape_id, duration, [property_name], additive=True)
        values = "".join(
            tag(
                "p:tav",
                {"tm": time},
                tag(
                    "p:val",
                    children=tag(
                        "p:strVal" if isinstance(value, str) else "p:fltVal",
                        {"val": value},
                    ),
                ),
            )
            for time, value in [(0, start), (100000, end)]
        )
        return tag(
            "p:anim",
            {"calcmode": "lin", "valueType": "num"},
            body + tag("p:tavLst", children=values),
        )

    def filter(self, shape_id, duration, filter_name, entrance=True, **timing):
        return tag(
            "p:animEffect",
            {"transition": "in" if entrance else "out", "filter": filter_name},
            self.behavior(shape_id, duration, hold=False, **timing),
        )

    def scale(self, shape_id, duration, amount, reverse=False):
        timing = {"autoRev": 1} if reverse else {}
        return tag(
            "p:animScale",
            children=self.behavior(shape_id, duration, **timing)
            + tag(
                "p:by",
                {
                    "x": round_half_away(amount * 100000),
                    "y": round_half_away(amount * 100000),
                },
            ),
        )

    def effect(self, animation, group_id=0):
        name = animation["effect"]
        preset, kind = PRESETS[name]
        node_id = self.allocate()
        shape_id = self.shape_ids[animation["elementId"]]
        duration = animation.get("durationMs", 500)
        entrance = kind == "entr"
        exit_effect = kind == "exit"
        direction = animation.get("direction", "up")
        subtype = 0
        if name in ["fly-in", "float-in", "peek-in"]:
            subtype = {"up": 4, "down": 1, "left": 2, "right": 8}[direction]
        elif name in ["fly-out", "float-out", "wipe-in", "wipe-out"]:
            subtype = {"up": 1, "down": 4, "left": 2, "right": 8}[direction]
        elif name == "zoom-in":
            subtype = 16
        elif name == "zoom-out":
            subtype = 32
        attrs = {"id": node_id}
        if (exit_effect and name != "disappear") or kind == "path":
            attrs["dur"] = duration
        attrs.update(
            {
                "presetID": preset,
                "presetClass": kind,
                "presetSubtype": subtype,
                "fill": "hold",
                "grpId": group_id,
                "nodeType": {
                    "onClick": "clickEffect",
                    "withPrevious": "withEffect",
                    "afterPrevious": "afterEffect",
                }.get(animation.get("trigger", "onClick"), "clickEffect"),
            }
        )
        if animation.get("repeat"):
            attrs["repeatCount"] = round_half_away(animation["repeat"] * 1000)
        easing = animation.get("easing")
        if easing in ["ease-in", "ease-in-out"]:
            attrs["accel"] = 50000 if easing == "ease-in-out" else 100000
        if easing in ["ease-out", "ease-in-out"]:
            attrs["decel"] = 50000 if easing == "ease-in-out" else 100000
        body = self.visibility(shape_id, True) if entrance else ""
        if name == "disappear":
            body = self.visibility(shape_id, False)
        elif name in [
            "fade-in",
            "fade-out",
            "wipe-in",
            "wipe-out",
            "float-in",
            "float-out",
            "peek-in",
        ]:
            filter_name = (
                f"wipe({direction})" if name.startswith(("wipe", "peek")) else "fade"
            )
            body += self.filter(shape_id, duration, filter_name, entrance)
        if name in ["fly-in", "fly-out", "float-in", "float-out", "peek-in", "rise-in"]:
            horizontal = direction in ["left", "right"]
            axis = "x" if horizontal else "y"
            extent = "w" if horizontal else "h"
            home = "#ppt_" + axis
            positive = (
                direction in ["up", "left"]
                if entrance
                else direction in ["down", "right"]
            )
            sign = "+" if positive else "-"
            if name.startswith("float"):
                away = home + sign + "0.1"
            elif name == "peek-in":
                away = home + sign + "#ppt_" + extent
            else:
                away = ("1+" if positive else "0-") + "#ppt_" + extent + "/2"
            body += self.interpolate(
                shape_id,
                duration,
                "ppt_" + axis,
                away if entrance else home,
                home if entrance else away,
            )
        elif name.startswith("zoom"):
            for property_name, small in [
                ("ppt_w", 0),
                ("ppt_h", 0),
                ("ppt_x", 0.5),
                ("ppt_y", 0.5),
            ]:
                home = "#" + property_name
                body += self.interpolate(
                    shape_id,
                    duration,
                    property_name,
                    small if entrance else home,
                    home if entrance else small,
                )
        elif name == "spin":
            body += tag(
                "p:animRot",
                {"by": round_half_away(animation.get("amount", 360) * 60000)},
                self.behavior(shape_id, duration, ["r"]),
            )
        elif name == "teeter":
            for index, amount in enumerate([2, -4, 4, -4, 2]):
                body += tag(
                    "p:animRot",
                    {"by": amount * 60000},
                    self.behavior(
                        shape_id,
                        duration * (0.1 if index == 0 else 0.2),
                        ["r"],
                        delay=round_half_away(index * duration * 0.2)
                        if index
                        else None,
                    ),
                )
        elif name == "grow-shrink":
            body += self.scale(shape_id, duration, animation.get("amount", 1.5))
        elif name == "pulse":
            body += self.filter(
                shape_id, duration, "fade", False, tmFilter="0, 0; .2, .5; .8, .5; 1, 0"
            )
            body += self.scale(
                shape_id, duration / 2, animation.get("amount", 1.05), True
            )
        elif name == "transparency":
            body += self.interpolate(
                shape_id,
                duration,
                "style.opacity",
                100000,
                round_half_away((1 - animation.get("amount", 0.5)) * 100000),
            )
        elif name in ["fill-color", "color-pulse"]:
            timing = {"autoRev": 1} if name == "color-pulse" else {}
            color = color_xml(animation.get("color", "#FFFF00"), self.theme)
            initial = (
                self.elements.get(animation["elementId"], {})
                .get("fill", {})
                .get("color", animation.get("color", "#FFFF00"))
            )
            body += tag(
                "p:animClr",
                {"calcmode": "lin", "valueType": "rgb"},
                self.behavior(
                    shape_id, duration, ["fillcolor"], additive=True, **timing
                )
                + tag("p:from", children=color_xml(initial, self.theme))
                + tag("p:to", children=color),
            )
        elif name == "motion-path":
            tokens = re.findall(
                r"[MLCQZmlcqz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)", animation.get("path", "")
            )
            converted = []
            coordinate = 0
            for token in tokens:
                if token.isalpha():
                    converted.append(token.upper())
                    coordinate = 0
                else:
                    value = float(token) / self.size[coordinate % 2]
                    converted.append(f"{value:.6f}".rstrip("0").rstrip(".") or "0")
                    coordinate += 1
            body += tag(
                "p:animMotion",
                {
                    "origin": "layout",
                    "path": " ".join(converted),
                    "pathEditMode": "relative",
                    "rAng": 0,
                    "ptsTypes": "",
                },
                self.behavior(shape_id, duration, ["ppt_x", "ppt_y"]),
            )
        if exit_effect and name != "disappear":
            body += self.visibility(shape_id, False, max(0, duration - 1))
        return tag(
            "p:par",
            children=tag(
                "p:cTn", attrs, condition(animation.get("delayMs", 0)) + children(body)
            ),
        )

    def write(self, animations):
        groups = []
        for animation in animations:
            if animation.get("trigger", "onClick") == "onClick" or not groups:
                groups.append([])
            groups[-1].append(animation)
        result = ""
        builds = []
        group_id = 0
        for group in groups:
            click_id = self.allocate()
            stages = []
            for animation in group:
                if animation.get("trigger") == "afterPrevious" or not stages:
                    stages.append([])
                stages[-1].append(animation)
            stage_xml = ""
            elapsed = 0
            for stage in stages:
                stage_id = self.allocate()
                effects = "".join(
                    self.effect(animation, group_id) for animation in stage
                )
                stage_xml += tag(
                    "p:par",
                    children=tag(
                        "p:cTn",
                        {"id": stage_id, "fill": "hold"},
                        condition(elapsed) + children(effects),
                    ),
                )
                elapsed += max(
                    a.get("delayMs", 0) + a.get("durationMs", 500) * a.get("repeat", 1)
                    for a in stage
                )
                builds.extend((self.shape_ids[a["elementId"]], group_id) for a in stage)
                group_id += 1
            result += tag(
                "p:par",
                children=tag(
                    "p:cTn",
                    {"id": click_id, "fill": "hold"},
                    condition("indefinite") + children(stage_xml),
                ),
            )
        sequence = tag(
            "p:cTn",
            {"id": 2, "dur": "indefinite", "nodeType": "mainSeq"},
            children(result),
        )
        for direction in ["Prev", "Next"]:
            sequence += tag(
                "p:" + direction.lower() + "CondLst",
                children=tag(
                    "p:cond",
                    {"evt": "on" + direction, "delay": 0},
                    tag("p:tgtEl", children=tag("p:sldTgt")),
                ),
            )
        root = tag(
            "p:par",
            children=tag(
                "p:cTn",
                {
                    "id": 1,
                    "dur": "indefinite",
                    "restart": "never",
                    "nodeType": "tmRoot",
                },
                children(tag("p:seq", {"concurrent": 1, "nextAc": "seek"}, sequence)),
            ),
        )
        builds = "".join(
            tag("p:bldP", {"spid": shape_id, "grpId": group_id, "animBg": 1})
            for shape_id, group_id in dict.fromkeys(builds)
        )
        return tag(
            "p:timing",
            children=tag("p:tnLst", children=root) + tag("p:bldLst", children=builds),
        )
