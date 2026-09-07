"""Convert SVG path commands to editable DrawingML custom geometry."""

import re

from .styles import preset_geometry
from .xml import round_half_away, tag

TOKEN = re.compile(r"[a-zA-Z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "Z": 0, "A": 7}


def point(x, y):
    return tag("a:pt", {"x": round_half_away(x), "y": round_half_away(y)})


def path_commands(path):
    tokens = TOKEN.findall(path)
    index = 0
    command = None
    x = y = start_x = start_y = 0
    last_control = None
    previous = None
    output = []
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command is None or command.upper() not in ARITY:
            raise NotImplementedError(f"SVG path command {command!r} is not supported")
        kind = command.upper()
        count = ARITY[kind]
        if kind == "Z":
            output.append(tag("a:close"))
            x, y = start_x, start_y
            command = None
            previous = kind
            continue
        values = list(map(float, tokens[index : index + count]))
        if len(values) != count:
            raise ValueError("Incomplete SVG path command")
        index += count
        relative = command.islower()

        def coordinates(a, b, x=x, y=y, relative=relative):
            return (a + x, b + y) if relative else (a, b)

        if kind in ["M", "L", "T"]:
            end = coordinates(*values)
            if kind == "T":
                control = (
                    (2 * x - last_control[0], 2 * y - last_control[1])
                    if previous in ["Q", "T"]
                    else (x, y)
                )
                output.append(
                    tag("a:quadBezTo", children=point(*control) + point(*end))
                )
                last_control = control
            else:
                output.append(
                    tag("a:moveTo" if kind == "M" else "a:lnTo", children=point(*end))
                )
            x, y = end
            if kind == "M":
                start_x, start_y = end
                command = "l" if relative else "L"
        elif kind in ["H", "V"]:
            if kind == "H":
                x = values[0] + (x if relative else 0)
            else:
                y = values[0] + (y if relative else 0)
            output.append(tag("a:lnTo", children=point(x, y)))
        elif kind == "A":
            end = coordinates(values[5], values[6])
            for segment in arc_segments(
                (x, y), values[:2], values[2], values[3], values[4], end
            ):
                output.append(
                    tag(
                        "a:lnTo" if segment[0] == "line" else "a:cubicBezTo",
                        children="".join(point(*p) for p in segment[1:]),
                    )
                )
            x, y = end
        else:
            pairs = [coordinates(*values[i : i + 2]) for i in range(0, len(values), 2)]
            if kind == "S":
                control = (
                    (2 * x - last_control[0], 2 * y - last_control[1])
                    if previous in ["C", "S"]
                    else (x, y)
                )
                pairs.insert(0, control)
            output.append(
                tag(
                    "a:quadBezTo" if kind == "Q" else "a:cubicBezTo",
                    children="".join(point(*p) for p in pairs),
                )
            )
            last_control = pairs[-2]
            x, y = pairs[-1]
        previous = kind
    return "".join(output)


def custom_geometry(path, viewbox):
    body = "".join(tag(name) for name in ["a:avLst", "a:gdLst", "a:ahLst", "a:cxnLst"])
    body += tag("a:rect", {"l": "l", "t": "t", "r": "r", "b": "b"})
    body += tag(
        "a:pathLst",
        children=tag("a:path", {"w": viewbox[0], "h": viewbox[1]}, path_commands(path)),
    )
    return tag("a:custGeom", children=body)


def shape_geometry(element):
    if element.get("shapeName") == "custom":
        return custom_geometry(element["path"], element["viewBox"])
    return preset_geometry(element.get("shapeName", "rect"), element.get("adjustments"))


def arc_segments(start, radii, rotation, large_arc, sweep, end):
    """SVG endpoint ellipse → cubic Bezier segments of at most 90 degrees."""
    import math

    x1, y1 = start
    x2, y2 = end
    rx, ry = map(abs, radii)
    if not rx or not ry:
        return [("line", end)]
    if start == end:
        return []
    phi = math.radians(rotation)
    cosine = math.cos(phi)
    sine = math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    local_x = cosine * dx + sine * dy
    local_y = -sine * dx + cosine * dy
    scale = local_x**2 / rx**2 + local_y**2 / ry**2
    if scale > 1:
        rx *= math.sqrt(scale)
        ry *= math.sqrt(scale)
    numerator = max(
        0, rx * rx * ry * ry - rx * rx * local_y * local_y - ry * ry * local_x * local_x
    )
    denominator = rx * rx * local_y * local_y + ry * ry * local_x * local_x
    factor = (-1 if bool(large_arc) == bool(sweep) else 1) * math.sqrt(
        numerator / denominator
    )
    center_x = factor * rx * local_y / ry
    center_y = -factor * ry * local_x / rx
    world_x = cosine * center_x - sine * center_y + (x1 + x2) / 2
    world_y = sine * center_x + cosine * center_y + (y1 + y2) / 2
    start_angle = math.atan2((local_y - center_y) / ry, (local_x - center_x) / rx)
    end_angle = math.atan2((-local_y - center_y) / ry, (-local_x - center_x) / rx)
    delta = end_angle - start_angle
    if sweep and delta < 0:
        delta += 2 * math.pi
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    count = max(1, math.ceil(abs(delta) / (math.pi / 2)))
    step = delta / count

    def position(angle):
        return world_x + rx * cosine * math.cos(angle) - ry * sine * math.sin(
            angle
        ), world_y + rx * sine * math.cos(angle) + ry * cosine * math.sin(angle)

    def tangent(angle):
        return -rx * cosine * math.sin(angle) - ry * sine * math.cos(
            angle
        ), -rx * sine * math.sin(angle) + ry * cosine * math.cos(angle)

    result = []
    for index in range(count):
        a = start_angle + index * step
        b = a + step
        factor = 4 / 3 * math.tan(step / 4)
        p, q = position(a), position(b)
        u, v = tangent(a), tangent(b)
        result.append(
            (
                "cubic",
                (p[0] + factor * u[0], p[1] + factor * u[1]),
                (q[0] - factor * v[0], q[1] - factor * v[1]),
                q,
            )
        )
    return result


def line_geometry(points, viewbox, curve="round"):
    """Sharp polylines, quadratic smoothing, or 12-unit rounded corners."""
    import math

    path = f"M{points[0][0]},{points[0][1]}"
    if curve == "smooth" and len(points) > 2:
        for index, p in enumerate(points[1:-1], 1):
            q = points[index + 1]
            end = (
                q
                if index == len(points) - 2
                else ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            )
            path += f" Q{p[0]},{p[1]} {end[0]},{end[1]}"
    elif curve == "round" and len(points) > 2:
        for index, p in enumerate(points[1:-1], 1):
            before, after = points[index - 1], points[index + 1]
            length_before = math.dist(before, p)
            length_after = math.dist(after, p)
            radius = min(12, length_before / 2, length_after / 2)
            entering = (
                tuple(
                    p[k] + (before[k] - p[k]) * radius / length_before for k in [0, 1]
                )
                if length_before
                else p
            )
            leaving = (
                tuple(p[k] + (after[k] - p[k]) * radius / length_after for k in [0, 1])
                if length_after
                else p
            )
            path += f" L{entering[0]},{entering[1]} Q{p[0]},{p[1]} {leaving[0]},{leaving[1]}"
        path += f" L{points[-1][0]},{points[-1][1]}"
    else:
        path += "".join(f" L{x},{y}" for x, y in points[1:])
    return custom_geometry(path, viewbox)
