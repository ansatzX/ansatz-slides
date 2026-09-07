"""Slide assembly and dispatch to readable element writers."""

import base64
import json

from .geometry import line_geometry, shape_geometry
from .images import blip_fill, image_bytes, image_info
from .package import PRESENTATION_MIME, Relationships
from .richtext import text_body
from .styles import fill_xml, line_xml, preset_geometry, shadow_xml, transform
from .tables import table_xml
from .xml import NAMESPACES, document, tag, text


def nonvisual(shape_id, name, kind="Sp", textbox=False, lock=False, metadata=None):
    specific = tag(
        f"p:cNv{kind}Pr",
        {"txBox": 1} if textbox else {},
        tag("a:graphicFrameLocks", {"noGrp": 1}) if lock else "",
    )
    extension = ""
    if metadata:
        metadata_kind, payload = metadata
        encoded = (
            base64.urlsafe_b64encode(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            )
            .decode()
            .rstrip("=")
        )
        extension = tag(
            "p:extLst",
            children=tag(
                "p:ext",
                {"uri": "{F5677B7D-0D2A-4D9B-9A5C-6D8D7D0E5A5D}"},
                text("pptd:" + metadata_kind, encoded, {"encoding": "base64url"}),
            ),
        )
    return tag(
        f"p:nv{kind}Pr",
        children=tag("p:cNvPr", {"id": shape_id, "name": name})
        + specific
        + tag("p:nvPr", children=extension),
    )


def group_prefix():
    body = tag(
        "p:nvGrpSpPr",
        children=tag("p:cNvPr", {"id": 1, "name": ""})
        + tag("p:cNvGrpSpPr")
        + tag("p:nvPr"),
    )
    coordinates = "".join(
        tag(name, attrs)
        for name, attrs in [
            ("a:off", {"x": 0, "y": 0}),
            ("a:ext", {"cx": 0, "cy": 0}),
            ("a:chOff", {"x": 0, "y": 0}),
            ("a:chExt", {"cx": 0, "cy": 0}),
        ]
    )
    return body + tag("p:grpSpPr", children=tag("a:xfrm", children=coordinates))


class SlideWriter:
    def __init__(
        self, package, number, theme, images, size=(960, 540), transition=None
    ):
        self.transition = transition
        self.size = size
        self.package, self.number, self.theme, self.images = (
            package,
            number,
            theme,
            images,
        )
        self.relationships = Relationships()
        self.relationships.add("slideLayout", "../slideLayouts/slideLayout1.xml")
        self.next_id = 2
        self.image_count = 0
        self.chart_count = 0
        self.shape_ids = {}

    def allocate_id(self):
        result = self.next_id
        self.next_id += 1
        return result

    def shape(self, element, shape_id):
        if (
            isinstance(element.get("fill"), dict)
            and element["fill"].get("type") == "image"
        ):
            return self.image_fill_shape(element, shape_id)
        properties = transform(element["bounds"], element) + shape_geometry(element)
        properties += fill_xml(
            element.get("fill"), self.theme, element.get("opacity", 1)
        )
        properties += line_xml(
            element.get("border"), self.theme, opacity=element.get("opacity", 1)
        ) + shadow_xml(element.get("shadow"), self.theme)
        return tag(
            "p:sp",
            children=nonvisual(shape_id, element["elementId"])
            + tag("p:spPr", children=properties),
        )

    def image_fill_shape(self, element, shape_id):
        fill = element["fill"]
        source = fill["src"]
        data = image_bytes(self.images.get(source, source))
        extension, width, height = image_info(data)
        self.image_count += 1
        filename = f"image{self.number}_{self.image_count}.{extension}"
        self.package.add("ppt/media/" + filename, data)
        relationship = self.relationships.add("image", "../media/" + filename)
        image_element = {
            **fill,
            "bounds": element["bounds"],
            "opacity": element.get("opacity", 1) * fill.get("opacity", 1),
        }
        paint = blip_fill(relationship, image_element, (width, height)).replace(
            "p:blipFill", "a:blipFill"
        )
        properties = (
            transform(element["bounds"], element)
            + shape_geometry(element)
            + paint
            + line_xml(None)
            + shadow_xml(element.get("shadow"), self.theme)
        )
        result = tag(
            "p:sp",
            children=nonvisual(shape_id, element["elementId"])
            + tag("p:spPr", children=properties),
        )
        if element.get("border"):
            result += self.shape(
                {
                    **element,
                    "fill": None,
                    "elementId": element["elementId"] + "-border",
                },
                self.allocate_id(),
            )
        return result

    def text(self, element, shape_id):
        properties = (
            transform(element["bounds"])
            + preset_geometry()
            + fill_xml(element["content"].get("backgroundColor"), self.theme)
            + line_xml(None)
        )
        result = tag(
            "p:sp",
            children=nonvisual(shape_id, element["elementId"], textbox=True)
            + tag("p:spPr", children=properties)
            + text_body(element["content"], self.theme, self.relationships),
        )
        if "\\(" in element["content"].get("text", ""):
            prefix = nonvisual(shape_id, element["elementId"], textbox=True) + tag(
                "p:spPr", children=properties
            )
            fallback = tag(
                "p:sp",
                children=prefix
                + text_body(
                    element["content"],
                    self.theme,
                    self.relationships,
                    native_math=False,
                ),
            )
            return tag(
                "mc:AlternateContent",
                children=tag("mc:Choice", {"Requires": "a14"}, result)
                + tag("mc:Fallback", {"xmlns": ""}, fallback),
            )
        return result

    def line(self, element, shape_id):
        points = [
            tuple(map(float, pair.split(","))) for pair in element["points"].split()
        ]
        geometry = line_geometry(
            points, element["viewBox"], element.get("curve", "round")
        )
        line = line_xml(
            element.get("border", {"width": 1, "color": "#000000"}), self.theme
        )
        arrows = element.get("arrow", [None, None])
        arrow_xml = "".join(
            tag(name, {"type": value})
            for name, value in zip(["a:headEnd", "a:tailEnd"], arrows)
            if value
        )
        if element.get("curve", "round") != "sharp":
            line = line.replace(">", ' cap="rnd">', 1)
        line = line.replace(
            "</a:ln>",
            (tag("a:round") if element.get("curve", "round") != "sharp" else "")
            + arrow_xml
            + "</a:ln>",
        )
        properties = (
            transform(element["bounds"], element)
            + geometry
            + tag("a:noFill")
            + line
            + shadow_xml(element.get("shadow"), self.theme)
        )
        return tag(
            "p:sp",
            children=nonvisual(
                shape_id,
                element["elementId"],
                metadata=(
                    "line",
                    {
                        key: element[key]
                        for key in ["viewBox", "points", "curve"]
                        if key in element
                    },
                ),
            )
            + tag("p:spPr", children=properties),
        )

    def icon(self, element, shape_id):
        # Compatibility behavior measured in the original writer: retain the
        # icon name for round-trip editing and emit its ellipse placeholder.
        properties = transform(element["bounds"], element) + preset_geometry("ellipse")
        properties += fill_xml(
            element.get("fill"), self.theme, element.get("opacity", 1)
        ) + line_xml(element.get("border"), self.theme)
        properties += shadow_xml(element.get("shadow"), self.theme)
        return tag(
            "p:sp",
            children=nonvisual(
                shape_id,
                element["elementId"],
                metadata=("icon", {"iconName": element["iconName"]}),
            )
            + tag("p:spPr", children=properties),
        )

    def image(self, element, shape_id):
        source = element["src"]
        if source not in self.images and not source.startswith("data:"):
            raise ValueError(f"Image resource not supplied: {source}")
        data = image_bytes(self.images.get(source, source))
        extension, width, height = image_info(data)
        self.image_count += 1
        filename = f"image{self.number}_{self.image_count}.{extension}"
        self.package.add("ppt/media/" + filename, data)
        relationship = self.relationships.add("image", "../media/" + filename)
        geometry = shape_geometry(element.get("cropShape", {}))
        properties = (
            transform(element["bounds"], element)
            + geometry
            + line_xml(None)
            + shadow_xml(element.get("shadow"), self.theme)
        )
        result = tag(
            "p:pic",
            children=nonvisual(shape_id, element["elementId"], "Pic")
            + blip_fill(
                relationship,
                {**element, "fit": {"mode": "fill"}} if extension == "svg" else element,
                (width, height),
            )
            + tag("p:spPr", children=properties),
        )
        if element.get("border"):
            border = {
                **element,
                **element.get("cropShape", {}),
                "elementId": element["elementId"] + "-border",
                "fill": None,
            }
            result += self.shape(border, self.allocate_id())
        return result

    def graphic_frame(self, element, shape_id, uri, content, lock=False):
        body = nonvisual(shape_id, element["elementId"], "GraphicFrame", lock=lock)
        body += transform(element["bounds"], name="p:xfrm")
        body += tag("a:graphic", children=tag("a:graphicData", {"uri": uri}, content))
        return tag("p:graphicFrame", children=body)

    def table(self, element, shape_id):
        return self.graphic_frame(
            element,
            shape_id,
            NAMESPACES["a"].replace("/main", "/table"),
            table_xml(element, self.theme),
            lock=True,
        )

    def chart(self, element, shape_id):
        from .charts import chart_xml

        self.chart_count += 1
        filename = f"chart{self.number}_{self.chart_count}.xml"
        self.package.add(
            "ppt/charts/" + filename,
            chart_xml(element, self.theme),
            "application/vnd.openxmlformats-officedocument.drawingml.chart+xml",
        )
        relationship = self.relationships.add("chart", "../charts/" + filename)
        return self.graphic_frame(
            element, shape_id, NAMESPACES["c"], tag("c:chart", {"r:id": relationship})
        )

    def write(self, page):
        background = ""
        if page.get("background"):
            background_fill = page["background"]
            if background_fill.get("type") == "image":
                source = background_fill["src"]
                data = image_bytes(self.images.get(source, source))
                extension, width, height = image_info(data)
                filename = f"image{self.number}_0.{extension}"
                self.package.add("ppt/media/" + filename, data)
                relationship = self.relationships.add("image", "../media/" + filename)
                paint = blip_fill(
                    relationship,
                    {**background_fill, "bounds": [0, 0, *self.size]},
                    (width, height),
                ).replace("p:blipFill", "a:blipFill")
            else:
                paint = fill_xml(background_fill, self.theme)
            background = tag("p:bg", children=tag("p:bgPr", children=paint))
        elements = []
        for element in page.get("elements", []):
            shape_id = self.allocate_id()
            self.shape_ids[element["elementId"]] = shape_id
            method = getattr(self, element["elementType"], None)
            if method is None:
                raise NotImplementedError(
                    f"Element {element['elementType']} is not reconstructed"
                )
            elements.append(method(element, shape_id))
        body = tag(
            "p:cSld",
            children=background
            + tag("p:spTree", children=group_prefix() + "".join(elements)),
        )
        body += tag("p:clrMapOvr", children=tag("a:masterClrMapping"))
        if self.transition and self.transition.get("effect") != "none":
            body += tag(
                "p:transition",
                {"spd": "fast", "advClick": 1},
                tag("p:" + self.transition.get("effect", "fade")),
            )
        if page.get("animations"):
            from .animations import TimingWriter

            body += TimingWriter(
                self.shape_ids, self.size, self.theme, page.get("elements", [])
            ).write(page["animations"])
        if page.get("notes"):
            from .notes import add_notes

            add_notes(self.package, self.number, page["notes"])
            self.relationships.add(
                "notesSlide", f"../notesSlides/notesSlide{self.number}.xml"
            )
        self.package.add(
            f"ppt/slides/slide{self.number}.xml",
            document("p:sld", {f"xmlns:{k}": v for k, v in NAMESPACES.items()}, body),
            PRESENTATION_MIME + "slide+xml",
        )
        self.package.add(
            f"ppt/slides/_rels/slide{self.number}.xml.rels", self.relationships.xml()
        )
