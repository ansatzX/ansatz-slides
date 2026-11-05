"""Deterministic local layout of existing elements; never rewrites content/styles."""

import copy
import math


def _number(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _bounds(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Layout bounds must be [x, y, width, height]")
    result = [_number(v, "Bounds") for v in value]
    if min(result[2:]) <= 0:
        raise ValueError("Layout width and height must be positive")
    return result


def apply_layout(page, operations):
    """Return a copy with only selected bounds changed, or fail without mutation.

    row/column translate items (single IDs or ID groups), preserving every size
    and relative group offset. Omitted gap distributes spare space evenly.
    segments resizes individual rectangles to explicit positive weight ratios.
    Final page geometry/text checks remain the caller's responsibility.
    """
    if not isinstance(operations, list) or not operations:
        raise ValueError("Layout must be a nonempty list of operations")
    result = copy.deepcopy(page)
    by_id = {}
    for element in result.get("elements", []):
        ident = element.get("elementId")
        if not isinstance(ident, str) or ident in by_id:
            raise ValueError("Layout requires unique element IDs")
        by_id[ident] = element
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("Layout operation must be an object")
        kind = operation.get("kind")
        required = {"kind", "items", "bounds"}
        allowed = required | (
            {"weights", "axis", "gap"} if kind == "segments" else {"gap", "align"}
        )
        if (
            kind not in ("row", "column", "segments")
            or not required <= operation.keys()
            or operation.keys() - allowed
        ):
            raise ValueError(
                "Layout needs kind row/column/segments, items, bounds and supported options"
            )
        items = operation["items"]
        if not isinstance(items, list) or not items:
            raise ValueError("Layout items must be a nonempty list")
        groups = []
        seen = set()
        for item in items:
            ids = [item] if isinstance(item, str) else item
            if (
                not isinstance(ids, list)
                or not ids
                or any(not isinstance(i, str) for i in ids)
            ):
                raise ValueError(
                    "Each layout item must be an element ID or a nonempty group of IDs"
                )
            group = []
            for ident in ids:
                if ident not in by_id or ident in seen:
                    raise ValueError(f"Unknown or repeated layout element: {ident}")
                seen.add(ident)
                element = by_id[ident]
                if element.get("rotation", 0):
                    raise ValueError(
                        "Layout of rotated elements requires explicit bounds edits"
                    )
                _bounds(element.get("bounds"))
                group.append(element)
            groups.append(group)
        x, y, width, height = _bounds(operation["bounds"])
        if kind == "segments":
            axis = operation.get("axis", "x")
            if axis not in ("x", "y") or any(
                len(g) != 1 or g[0].get("elementType") != "shape" for g in groups
            ):
                raise ValueError("Segments require individual shapes and axis x or y")
            weights = operation.get("weights")
            if not isinstance(weights, list) or len(weights) != len(groups):
                raise ValueError("Segments need one positive weight per item")
            weights = [_number(v, "Weight") for v in weights]
            if min(weights) <= 0:
                raise ValueError("Segment weights must be positive")
            gap = _number(operation.get("gap", 0), "Gap")
            extent = width if axis == "x" else height
            available = extent - gap * (len(groups) - 1)
            if gap < 0 or available <= 0:
                raise ValueError("Segment gaps leave no positive space")
            scale = max(weights)
            normalized = [v / scale for v in weights]
            total = math.fsum(normalized)
            origin = x if axis == "x" else y
            cursor = origin
            for i, group in enumerate(groups):
                # Shared boundaries avoid cumulative drift outside the region.
                end = (
                    origin + extent
                    if i == len(groups) - 1
                    else origin
                    + available * (math.fsum(normalized[: i + 1]) / total)
                    + gap * i
                )
                length = end - cursor
                if length <= 0:
                    raise ValueError("Segment weight ratio is too small")
                group[0]["bounds"] = (
                    [cursor, y, length, height]
                    if axis == "x"
                    else [x, cursor, width, length]
                )
                cursor = end + gap
            continue
        axis = 0 if kind == "row" else 1
        cross = 1 - axis
        start = [x, y]
        span = [width, height]
        boxes = []
        for group in groups:
            left = min(e["bounds"][0] for e in group)
            top = min(e["bounds"][1] for e in group)
            right = max(e["bounds"][0] + e["bounds"][2] for e in group)
            bottom = max(e["bounds"][1] + e["bounds"][3] for e in group)
            boxes.append([left, top, right - left, bottom - top])
        used = sum(b[axis + 2] for b in boxes)
        if used > span[axis] + 1e-8 or any(
            b[cross + 2] > span[cross] + 1e-8 for b in boxes
        ):
            raise ValueError(
                "Items do not fit layout bounds; enlarge the region or explicitly resize elements"
            )
        gap = (
            _number(operation["gap"], "Gap")
            if "gap" in operation
            else ((span[axis] - used) / (len(groups) - 1) if len(groups) > 1 else 0)
        )
        if gap < 0 or used + gap * (len(groups) - 1) > span[axis] + 1e-8:
            raise ValueError("Items and gaps do not fit layout bounds")
        align = operation.get("align", "center")
        if align not in ("start", "center", "end"):
            raise ValueError("Layout align must be start, center or end")
        factor = {"start": 0, "center": 0.5, "end": 1}[align]
        cursor = start[axis]
        for group, box in zip(groups, boxes):
            offset = [0, 0]
            offset[axis] = cursor - box[axis]
            offset[cross] = (
                start[cross] + (span[cross] - box[cross + 2]) * factor - box[cross]
            )
            for element in group:
                bx, by, bw, bh = element["bounds"]
                element["bounds"] = [bx + offset[0], by + offset[1], bw, bh]
            cursor += box[axis + 2] + gap
    return result
