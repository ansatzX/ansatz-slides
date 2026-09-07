"""Image resources and crop mathematics, independent of a browser or WASM."""

import base64
import struct
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
        viewbox = root.get("viewBox", "0 0 1 1").replace(",", " ").split()
        return "svg", float(viewbox[2]), float(viewbox[3])
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
