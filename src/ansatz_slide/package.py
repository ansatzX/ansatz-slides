"""Open Packaging Convention parts, content types and typed relationships.

PPTX is a ZIP of XML parts. This module owns package paths and relationship
allocation; element writers never assemble a ZIP or guess relationship IDs.
"""

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .xml import NAMESPACES, document, emu, tag, text

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = NAMESPACES["r"] + "/"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PRESENTATION_MIME = "application/vnd.openxmlformats-officedocument.presentationml."
DRAWING_MIME = "application/vnd.openxmlformats-officedocument.drawingml."


@dataclass
class Relationships:
    entries: list = field(default_factory=list)

    def add(self, kind, target, external=False):
        relationship_id = f"rId{len(self.entries) + 1}"
        attrs = {"Id": relationship_id, "Type": OFFICE_REL + kind, "Target": target}
        if external:
            attrs["TargetMode"] = "External"
        self.entries.append(attrs)
        return relationship_id

    def xml(self):
        return document(
            "Relationships",
            {"xmlns": REL_NS},
            "".join(tag("Relationship", entry) for entry in self.entries),
        )


class Package:
    def __init__(self):
        self.parts = {}
        self.types = {}
        templates = Path(__file__).with_name("templates")
        for path in sorted(templates.rglob("*")):
            if path.is_file():
                self.parts[path.relative_to(templates).as_posix()] = path.read_bytes()

    def add(self, name, data, content_type=None):
        if name in self.parts:
            raise ValueError(f"Duplicate PPTX part: {name}")
        self.parts[name] = (
            data.encode("utf-8") if isinstance(data, str) else bytes(data)
        )
        if content_type:
            self.types[name] = content_type

    def finish(self, size, slide_count):
        relationships = Relationships()
        relationships.add("slideMaster", "slideMasters/slideMaster1.xml")
        relationships.add("theme", "theme/theme1.xml")
        slides = "".join(
            tag(
                "p:sldId",
                {
                    "id": 256 + index,
                    "r:id": relationships.add("slide", f"slides/slide{index + 1}.xml"),
                },
            )
            for index in range(slide_count)
        )
        notes_id = (
            relationships.add("notesMaster", "notesMasters/notesMaster1.xml")
            if "ppt/notesMasters/notesMaster1.xml" in self.parts
            else None
        )
        for kind in ["presProps", "viewProps", "tableStyles"]:
            relationships.add(kind, f"{kind}.xml")
        self.add("ppt/_rels/presentation.xml.rels", relationships.xml())
        width, height = map(emu, size)
        body = tag(
            "p:sldMasterIdLst",
            children=tag("p:sldMasterId", {"id": 2147483648, "r:id": "rId1"}),
        )
        body += tag("p:sldIdLst", children=slides)
        if notes_id:
            body += tag(
                "p:notesMasterIdLst",
                children=tag("p:notesMasterId", {"r:id": notes_id}),
            )
        body += tag("p:sldSz", {"cx": width, "cy": height, "type": "custom"})
        body += tag("p:notesSz", {"cx": width, "cy": height})
        self.add(
            "ppt/presentation.xml",
            document(
                "p:presentation",
                {
                    **{f"xmlns:{k}": NAMESPACES[k] for k in ["a", "r", "p"]},
                    "autoCompressPictures": 0,
                },
                body,
            ),
        )
        self.add(
            "docProps/app.xml",
            document(
                "Properties",
                {
                    "xmlns": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
                },
                text("Application", "Neo Design") + text("Slides", slide_count),
            ),
        )
        static_types = {
            "docProps/app.xml": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
            "docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
            "docProps/custom.xml": "application/vnd.openxmlformats-officedocument.custom-properties+xml",
            "ppt/presentation.xml": PRESENTATION_MIME + "presentation.main+xml",
            "ppt/theme/theme1.xml": "application/vnd.openxmlformats-officedocument.theme+xml",
            "ppt/slideMasters/slideMaster1.xml": PRESENTATION_MIME + "slideMaster+xml",
            "ppt/slideLayouts/slideLayout1.xml": PRESENTATION_MIME + "slideLayout+xml",
            **{
                f"ppt/{kind}.xml": PRESENTATION_MIME + kind + "+xml"
                for kind in ["presProps", "viewProps", "tableStyles"]
            },
        }
        # Table styles use the DrawingML media type, not presentationml.
        static_types["ppt/tableStyles.xml"] = (
            "application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"
        )
        defaults = {
            "rels": "application/vnd.openxmlformats-package.relationships+xml",
            "xml": "application/xml",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "svg": "image/svg+xml",
        }
        body = "".join(
            tag("Default", {"Extension": ext, "ContentType": mime})
            for ext, mime in defaults.items()
        )
        body += "".join(
            tag("Override", {"PartName": "/" + name, "ContentType": mime})
            for name, mime in {
                **static_types,
                **dict(
                    sorted(
                        self.types.items(),
                        key=lambda pair: (
                            0
                            if "/notesMasters/" in pair[0]
                            else 1
                            if "/slides/" in pair[0]
                            else 2,
                            pair[0],
                        ),
                    )
                ),
            }.items()
        )
        self.add("[Content_Types].xml", document("Types", {"xmlns": CONTENT_NS}, body))
        stream = BytesIO()
        with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
            for name, data in self.parts.items():
                info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, data)
        return stream.getvalue()
