"""Inspect the actual output ZIP and its internal relationships, not a preview."""

import io
import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET


def inspect_pptx(source):
    source = io.BytesIO(source) if isinstance(source, bytes) else Path(source)
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP part names")
        bad = archive.testzip()
        if bad:
            raise ValueError("Corrupt ZIP part: " + bad)
        required = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"}
        if not required.issubset(names):
            raise ValueError("Missing required PPTX parts")
        for name in names:
            if name.endswith((".xml", ".rels")):
                tree = ET.fromstring(archive.read(name))
                if name.endswith(".rels"):
                    base = posixpath.dirname(posixpath.dirname(name))
                    ids = set()
                    for rel in tree:
                        if rel.get("Id") in ids:
                            raise ValueError("Duplicate relationship ID in " + name)
                        ids.add(rel.get("Id"))
                        if rel.get("TargetMode") == "External":
                            continue
                        target = unquote(rel.attrib["Target"]).split("#", 1)[0]
                        target = (
                            target.lstrip("/")
                            if target.startswith("/")
                            else posixpath.normpath(posixpath.join(base, target))
                        )
                        if target not in names:
                            raise ValueError(f"Broken relationship: {name} -> {target}")
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        slides = presentation.findall(
            "{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"
        )
        return {
            "ok": True,
            "parts": len(names),
            "pageCount": len(slides),
            "visualReview": "not performed",
        }
