"""Image resources and crop mathematics, independent of a browser or WASM."""

import base64
import struct
import math
import re
from xml.etree import ElementTree as ET

from .xml import round_half_away, tag


def image_bytes(value):
    if isinstance(value, dict) and "base64" in value:
        return base64.b64decode(value["base64"])
    if isinstance(value, str) and value.startswith("data:"):
        return base64.b64decode(value.split(",", 1)[1])
    return bytes(value)


def image_info(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", *struct.unpack(">II", data[16:24])
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif", *struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        cursor = 2
        while cursor < len(data):
            if data[cursor] != 255:
                cursor += 1
                continue
            while data[cursor] == 255:
                cursor += 1
            marker = data[cursor]
            cursor += 1
            if marker in [0, 1, 216, 217] or 208 <= marker <= 215:
                continue
            length = int.from_bytes(data[cursor : cursor + 2], "big")
            if marker in [
                192,
                193,
                194,
                195,
                197,
                198,
                199,
                201,
                202,
                203,
                205,
                206,
                207,
            ]:
                height, width = struct.unpack(">HH", data[cursor + 3 : cursor + 7])
                return "jpg", width, height
            cursor += length
    if b"<svg" in data[:4096]:
        root = ET.fromstring(data)
        if root.get("viewBox") is not None:
            values = root.get("viewBox").replace(",", " ").split()
            if len(values) != 4:
                raise ValueError("SVG viewBox must contain four finite numbers")
            values = [float(v) for v in values]
            if not all(math.isfinite(v) for v in values):
                raise ValueError("SVG viewBox must contain four finite numbers")
            width, height = values[2:]
        else:
            units = {"": 1, "px": 1, "in": 96, "cm": 96/2.54,
                     "mm": 96/25.4, "pt": 96/72, "pc": 16, "Q": 96/101.6}
            sizes = []
            for key in ("width", "height"):
                match = re.fullmatch(r"\s*([+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(px|in|cm|mm|pt|pc|Q)?\s*", root.get(key, ""))
                if not match:
                    raise ValueError("SVG without viewBox needs absolute width and height")
                sizes.append(float(match[1]) * units[match[2] or ""])
            width, height = sizes
        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
            raise ValueError("SVG dimensions must be positive and finite")
        return "svg", width, height
    raise ValueError("Image must be PNG, JPEG, GIF or SVG")


def crop_attributes(element, image_size):
    crop = element.get("crop")
    if crop is not None:
        return {
            short: round_half_away(crop.get(long, 0) * 100000)
            for long, short in [
                ("left", "l"),
                ("top", "t"),
                ("right", "r"),
                ("bottom", "b"),
            ]
            if crop.get(long, 0)
        }
    mode = element.get("fit", {}).get("mode", "fill")
    if mode == "fill":
        return {}
    width, height = element["bounds"][2:]
    image_width, image_height = image_size
    scale = (min if mode == "contain" else max)(
        width / image_width, height / image_height
    )
    horizontal = (1 - width / (image_width * scale)) / 2
    vertical = (1 - height / (image_height * scale)) / 2
    return {
        key: round_half_away(value * 100000)
        for key, value in [
            ("l", horizontal),
            ("r", horizontal),
            ("t", vertical),
            ("b", vertical),
        ]
        if abs(value) > 1e-10
    } or (
        {"l": 0, "r": 0}
        if image_width / image_height >= width / height
        else {"t": 0, "b": 0}
    )


def blip_fill(relationship_id, element, image_size):
    opacity = element.get("opacity", 1)
    effects = (
        tag("a:alphaModFix", {"amt": round_half_away(opacity * 100000)})
        if opacity != 1
        else ""
    )
    body = tag("a:blip", {"r:embed": relationship_id}, effects)
    crop = crop_attributes(element, image_size)
    if crop:
        body += tag("a:srcRect", crop)
    body += tag("a:stretch", children=tag("a:fillRect"))
    return tag("p:blipFill", children=body)
