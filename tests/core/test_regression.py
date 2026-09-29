"""Run every recorded differential case without the original binary writer.

The expected hashes were measured from original output, never from this source
implementation. Theme display names and the provenance statement were updated
only for the requested source-format terminology change; all other recorded
parts retain their original fingerprints. XML fingerprints compare expanded names, attributes, text and
ordered child nodes, ignoring only serializer syntax and ZIP metadata.
"""

import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ansatz_slide import export_pptx


def xml_tree(node):
    return [
        node.tag,
        sorted(node.attrib.items()),
        node.text or "",
        [xml_tree(child) for child in node],
        node.tail or "",
    ]


def corrected_semantics_projection(root, case):
    """Compare legacy fingerprints after reversing only documented bug fixes.

    Frozen hashes stay untouched. Actual break nodes and spacing are asserted
    before projection; test_review_semantics independently checks new semantics.
    """
    ns = {'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    for parent in root.iter():
        for br in list(parent.findall('a:br', ns)):
            children = list(parent); index = children.index(br)
            assert br.find('a:rPr', ns) is not None
            prev = children[index-1] if index else None
            nxt = children[index+1] if index+1 < len(children) else None
            parent.remove(br)
            if (prev is not None and nxt is not None and
                prev.tag == nxt.tag == '{'+ns['a']+'}r' and
                xml_tree(prev.find('a:rPr', ns)) == xml_tree(nxt.find('a:rPr', ns))):
                left, right = prev.find('a:t',ns), nxt.find('a:t',ns)
                left.text = (left.text or '') + (right.text or '')
                parent.remove(nxt)
    if case == 'cases-special/svg':
        for fill in root.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}blipFill'):
            crop = fill.find('a:srcRect', ns)
            assert crop is not None and crop.attrib == {'l':'0','r':'0'}
            fill.remove(crop)
    if case == 'cases-edges/rich-css':
        runs = root.findall('.//a:rPr', ns)
        assert len(runs) == 1 and runs[0].get('spc') == '100' and runs[0].get('kern') == '0'
        del runs[0].attrib['spc']; del runs[0].attrib['kern']
    return root


def fingerprints(data, case=None):
    result = {}
    with ZipFile(io.BytesIO(data)) as archive:
        if len(set(archive.namelist())) != len(archive.namelist()):
            raise AssertionError("Duplicate package part")
        for name in archive.namelist():
            value = archive.read(name)
            if name.endswith((".xml", ".rels")):
                value = json.dumps(
                    xml_tree(corrected_semantics_projection(ET.fromstring(value), case)
                             if case and name.startswith("ppt/slides/slide") and name.endswith(".xml")
                             else ET.fromstring(value)),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            result[name] = hashlib.sha256(value).hexdigest()
    return result


@patch('ansatz_slide.occupancy.require_pages', return_value=[])
def main(_geometry_gate):
    # Frozen legacy inputs exercise OOXML serialization, including deliberately
    # overlapping/out-of-canvas cases. Keep their independent byte expectations;
    # mandatory gate behavior is covered without mocks in test_geometry_gate.
    directory = Path(__file__).with_name("fixtures")
    expected = json.loads((directory / "expected.json").read_text())
    failures = []
    count = 0
    for path in sorted(directory.glob("cases-*.json")):
        fixture = json.loads(path.read_text())
        for case in fixture["cases"]:
            count += 1
            name = path.stem + "/" + case["name"]
            if "error" in expected[name]:
                try:
                    export_pptx(case["pptd"], fixture["options"])
                except ValueError as error:
                    if str(error) != "pptx.yaml pages must be an array":
                        failures.append(name + ": wrong validation error")
                else:
                    failures.append(name + ": invalid input accepted")
                continue
            try:
                actual = fingerprints(export_pptx(case["pptd"], fixture["options"]), name)
                wanted = expected[name]["parts"]
                mismatches = sorted(
                    key
                    for key in set(actual) | set(wanted)
                    if actual.get(key) != wanted.get(key)
                )
                if mismatches:
                    failures.append(name + ": " + ", ".join(mismatches))
            except (
                Exception
            ) as error:  # Report the failing case, then test the remaining cases.
                failures.append(name + ": " + repr(error))
    if failures:
        print("\n".join(failures))
        raise AssertionError("\n".join(failures))
    print(
        f"{count} differential cases passed; XML trees and binary parts match frozen outputs after explicit break/spacing/SVG-fit correction projection."
    )


class RecordedOutputTests(unittest.TestCase):
    def test_recorded_output_fingerprints(self):
        main()


if __name__ == "__main__":
    unittest.main()
