"""Speaker notes and their explicit slide/master relationships."""

from pathlib import Path

from .package import PRESENTATION_MIME, Relationships
from .styles import preset_geometry, transform
from .xml import NAMESPACES, document, tag, text


def add_notes(package, slide_number, value):
    if "ppt/notesMasters/notesMaster1.xml" not in package.parts:
        folder = Path(__file__).with_name("notes_templates")
        for path in folder.rglob("*"):
            if path.is_file():
                name = path.relative_to(folder).as_posix()
                package.add(
                    name,
                    path.read_bytes(),
                    PRESENTATION_MIME + "notesMaster+xml"
                    if name.endswith("notesMaster1.xml")
                    else None,
                )
    group = tag(
        "p:nvGrpSpPr",
        children=tag("p:cNvPr", {"id": 1, "name": ""})
        + tag("p:cNvGrpSpPr")
        + tag("p:nvPr"),
    ) + tag("p:grpSpPr")
    nonvisual = tag(
        "p:nvSpPr",
        children=tag("p:cNvPr", {"id": 2, "name": "Notes Placeholder 1"})
        + tag("p:cNvSpPr", {"txBox": 1})
        + tag("p:nvPr", children=tag("p:ph", {"type": "body"})),
    )
    properties = tag(
        "p:spPr", children=transform([0, 0, 0, 0]) + preset_geometry() + tag("a:noFill")
    )
    paragraphs = "".join(
        tag(
            "a:p",
            children=tag(
                "a:r",
                children=tag("a:rPr", {"lang": "en-US", "sz": 1200, "noProof": 1})
                + text("a:t", line),
            ),
        )
        for line in str(value).splitlines()
    )
    textbox = tag("p:txBody", children=tag("a:bodyPr") + tag("a:lstStyle") + paragraphs)
    body = tag(
        "p:cSld",
        children=tag(
            "p:spTree",
            children=group + tag("p:sp", children=nonvisual + properties + textbox),
        ),
    )
    body += tag("p:clrMapOvr", children=tag("a:masterClrMapping"))
    package.add(
        f"ppt/notesSlides/notesSlide{slide_number}.xml",
        document(
            "p:notes",
            {f"xmlns:{key}": NAMESPACES[key] for key in ["p", "a", "r"]},
            body,
        ),
        PRESENTATION_MIME + "notesSlide+xml",
    )
    rels = Relationships()
    rels.add("notesMaster", "../notesMasters/notesMaster1.xml")
    rels.add("slide", f"../slides/slide{slide_number}.xml")
    package.add(f"ppt/notesSlides/_rels/notesSlide{slide_number}.xml.rels", rels.xml())
