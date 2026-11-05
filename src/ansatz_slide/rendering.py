"""Render a prepared PPTX through local LibreOffice and Poppler."""

import copy
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from .package import Package
from .slides import SlideWriter


def run_command(command, cwd):
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError(
            Path(command[0]).name
            + " failed: "
            + (result.stdout + result.stderr)[-2000:]
        )


def verify_table_text(source, pdf, folder):
    """Reject missing table text in the actual consumer PDF, not a size test."""
    with ZipFile(source) as archive:
        slides = sorted(
            (
                n
                for n in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide[0-9]+\.xml", n)
            ),
            key=lambda n: int(re.search(r"slide([0-9]+)", n).group(1)),
        )
        for number, name in enumerate(slides, 1):
            root = ET.fromstring(archive.read(name))
            texts = [
                "".join(
                    t.text or ""
                    for t in cell.findall(
                        ".//{http://schemas.openxmlformats.org/drawingml/2006/main}t"
                    )
                )
                for cell in root.findall(
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}tc"
                )
            ]
            texts = [t for t in texts if t.strip()]
            if not texts:
                continue
            extractor = shutil.which("pdftotext")
            if not extractor:
                raise RuntimeError(
                    "Table rendering verification requires Poppler pdftotext"
                )
            destination = folder / f"table-text-{number}.txt"
            run_command(
                [
                    extractor,
                    "-f",
                    str(number),
                    "-l",
                    str(number),
                    "-layout",
                    str(pdf),
                    str(destination),
                ],
                folder,
            )
            normalize = lambda text: "".join(text.split()).replace("\u00ad", "")
            rendered = normalize(destination.read_text(encoding="utf-8"))
            missing = [text for text in texts if normalize(text) not in rendered]
            if missing:
                raise RuntimeError(
                    "Rendered table text is missing or changed on page "
                    + str(number)
                    + "; inspect LibreOffice font/merged-cell compatibility. Evidence: "
                    + str(destination)
                )


def render_pptx(source, folder, width=1600):
    """使用本地演示软件工具将给定 PPTX 渲染为静态 PNG 页面。

    栅格化前会将实际生成的 PDF 与源 PPTX 中的表格文本核对。该路径记录的是
    LibreOffice 证据，不验证原生 Office Math 或目标消费程序中的呈现。
    """
    office = shutil.which("soffice") or shutil.which("libreoffice")
    poppler = shutil.which("pdftoppm")
    if not office or not poppler:
        raise RuntimeError(
            "Page check needs LibreOffice (soffice) and Poppler (pdftoppm)"
        )
    profile = (folder / "office-profile").resolve().as_uri()
    run_command(
        [
            office,
            "-env:UserInstallation=" + profile,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(folder),
            str(source),
        ],
        folder,
    )
    pdf = folder / (source.stem + ".pdf")
    if not pdf.is_file():
        raise RuntimeError("Office did not produce a PDF")
    verify_table_text(source, pdf, folder)
    run_command(
        [poppler, "-scale-to", str(width), "-png", str(pdf), str(folder / "page")],
        folder,
    )
    shutil.rmtree(folder / "office-profile", ignore_errors=True)
    return {
        "name": "LibreOffice + pdftoppm",
        "maxPixels": width,
        "scope": "static render of the supplied PPTX; native PowerPoint/WPS unverified",
    }


def table_ink_bounds(path):
    """Read Poppler's binary graymap without an imaging dependency."""
    with Path(path).open("rb") as stream:

        def tokens():
            while True:
                line = stream.readline()
                if not line:
                    raise ValueError("Truncated PGM header")
                if not line.startswith(b"#"):
                    return line.split()

        if tokens() != [b"P5"]:
            raise ValueError("Expected binary graymap")
        width, height = map(int, tokens())
        if tokens() != [b"255"]:
            raise ValueError("Expected 8-bit graymap")
        left, top, right, bottom = width, height, -1, -1
        for y in range(height):
            row = stream.read(width)
            if len(row) != width:
                raise ValueError("Truncated graymap")
            pixels = [x for x, value in enumerate(row) if value < 240]
            if pixels:
                left = min(left, pixels[0])
                right = max(right, pixels[-1] + 1)
                top = min(top, y)
                bottom = y + 1
    return None if right < 0 else [left / 2, top / 2, right / 2, bottom / 2]


def check_tables(elements, theme, folder):
    """测量 LibreOffice 中独立表格的扩展范围，不改变表格内容。

    单元格填充用于形成表格剪影；源稿列宽、行设置、字体、合并和边框在探测中
    保持不变。结果是此消费程序的测量范围，不代表 PowerPoint/WPS 视觉验收。
    """
    if not elements:
        return []
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    office = shutil.which("soffice") or shutil.which("libreoffice")
    raster = shutil.which("pdftoppm")
    if not office or not raster:
        raise RuntimeError("Table measurement requires LibreOffice and Poppler")
    margin = 72
    width = max(1000, max(e["bounds"][2] for e in elements) + 2 * margin)
    height = max(4000, max(e["bounds"][3] for e in elements) + 2 * margin)
    if max(width, height) > 10000:
        raise ValueError("Table measurement probe too large; split the table")
    package = Package()
    for number, element in enumerate(elements, 1):
        candidate = copy.deepcopy(element)
        candidate["bounds"][:2] = [margin, margin]
        candidate.pop("rotation", None)
        candidate.pop("animations", None)
        for row in candidate["rows"]:
            for cell in row:
                cell["fill"] = {"type": "solid", "color": "#000000"}
        SlideWriter(
            package,
            number,
            theme or {},
            {},
            [width, height],
            {"effect": "none", "speed": "fast"},
        ).write({"elements": [candidate]})
    source = folder / "table-probe.pptx"
    source.write_bytes(package.finish([width, height], len(elements)))
    profile = folder / "office-profile"
    try:
        run_command(
            [
                office,
                "-env:UserInstallation=" + profile.resolve().as_uri(),
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(folder.resolve()),
                str(source.resolve()),
            ],
            folder,
        )
        pdf = folder / "table-probe.pdf"
        verify_table_text(source, pdf, folder)
        reports = []
        for number, element in enumerate(elements, 1):
            prefix = folder / f"table-{number}"
            run_command(
                [
                    raster,
                    "-f",
                    str(number),
                    "-l",
                    str(number),
                    "-singlefile",
                    "-r",
                    "144",
                    "-gray",
                    str(pdf.resolve()),
                    str(prefix.resolve()),
                ],
                folder,
            )
            bounds = table_ink_bounds(prefix.with_suffix(".pgm"))
            item = {
                "elementId": element["elementId"],
                "bounds": element["bounds"],
                "status": "unverified",
                "scope": "Isolated consumer table silhouette, including cell fills and text; 0.5 pt raster resolution. Glyph appearance and PowerPoint/WPS remain unverified.",
                "evidence": str(prefix.with_suffix(".pgm")),
            }
            if bounds is None:
                item["reason"] = "Renderer produced no table silhouette"
            else:
                left, top, right, bottom = [v - margin for v in bounds]
                w, h = element["bounds"][2:]
                item.update(
                    measuredBounds=[left, top, right - left, bottom - top],
                    requiredWidth=right,
                    requiredHeight=bottom,
                )
                if bounds[2] >= width - 1 or bounds[3] >= height - 1:
                    item["reason"] = (
                        "Probe limit reached; table may be clipped; split before retrying"
                    )
                else:
                    edges = {
                        key: round(value, 2)
                        for key, value in [
                            ("left", -left),
                            ("top", -top),
                            ("right", right - w),
                            ("bottom", bottom - h),
                        ]
                        if value > 1
                    }
                    if edges:
                        item.update(
                            status="overflow",
                            overflowEdges=edges,
                            reason=f"Renderer expands table beyond declared bounds: {edges}",
                            repairHint="Enlarge the table bounds to the measured extent and reposition neighbors, or split rows while preserving content. No universal minimum row height is assumed.",
                        )
                    else:
                        item["status"] = "passed"
            reports.append(item)
        return reports
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def text_ink_bounds(pdf, number, folder, measured, frame, *, margin=72):
    tool = shutil.which("pdftoppm")
    if not tool:
        return None
    left, top, width, height = measured
    x0 = max(0, margin + min(0, left) - 8)
    y0 = max(0, margin + min(0, top) - 8)
    x1 = margin + max(frame[0], left + width) + 8
    y1 = margin + max(frame[1], top + height) + 8
    scale = 2
    w = int((x1 - x0) * scale) + 2
    h = int((y1 - y0) * scale) + 2
    if w * h > 12_000_000:
        return None
    prefix = (Path(folder) / f"ink-{number}").resolve()
    run_command(
        [
            tool,
            "-f",
            str(number),
            "-l",
            str(number),
            "-r",
            "144",
            "-x",
            str(int(x0 * scale)),
            "-y",
            str(int(y0 * scale)),
            "-W",
            str(w),
            "-H",
            str(h),
            "-gray",
            "-singlefile",
            str(pdf),
            str(prefix),
        ],
        folder,
    )
    data = prefix.with_suffix(".pgm").read_bytes()
    match = re.match(rb"P5\s+(?:#[^\n]*\n\s*)?(\d+)\s+(\d+)\s+255\s", data)
    if not match:
        return None
    w, h = map(int, match.groups())
    pixels = data[match.end() :]
    if len(pixels) != w * h:
        return None
    xmin = w
    ymin = h
    xmax = ymax = -1
    for y in range(h):
        row = pixels[y * w : (y + 1) * w]
        dark = [x for x, value in enumerate(row) if value < 245]
        if dark:
            xmin = min(xmin, dark[0])
            xmax = max(xmax, dark[-1])
            ymin = min(ymin, y)
            ymax = y
    if xmax < 0:
        return None
    return [
        int(x0 * scale) / scale + xmin / scale - margin,
        int(y0 * scale) / scale + ymin / scale - margin,
        (xmax - xmin + 1) / scale,
        (ymax - ymin + 1) / scale,
    ]


def check_pages(size, pages, theme, folder):
    """Share probe conversion across pages, preserving page-local element IDs.

    按探测数量分组以限制转换时间与消费程序内存。临时元素 ID 用于区分不同
    页面上的重复源 ID，并在报告前映射回原 ID。每次都会重新测量，不复用旧结果。
    """
    from .typography import check_page

    folder = Path(folder)
    reports = []
    groups = []
    group = []
    count = 0
    for number, page in enumerate(pages, 1):
        weight = sum(
            2
            if isinstance(e.get("content", {}).get("align"), list)
            and e["content"]["align"][-1] in ("middle", "bottom")
            else 1
            for e in page.get("elements", [])
        )
        if group and count + weight > 128:
            groups.append(group)
            group = []
            count = 0
        group.append((number, page))
        count += weight
    if group:
        groups.append(group)
    for batch_number, group in enumerate(groups, 1):
        combined = {"elements": []}
        identities = {}
        for number, page in group:
            for index, element in enumerate(page.get("elements", [])):
                candidate = copy.deepcopy(element)
                key = f"page-{number}-element-{index}"
                identities[key] = (number, element.get("elementId"))
                candidate["elementId"] = key
                combined["elements"].append(candidate)
        measured = check_page(size, combined, theme, folder / f"batch-{batch_number}")
        per_page = {}
        for number, page in group:
            report = {
                k: copy.deepcopy(v)
                for k, v in measured.items()
                if k not in ("elements", "unmeasuredObjects", "status")
            }
            report.update(
                page=number,
                status="passed",
                elements=[],
                unmeasuredObjects=[
                    e.get("elementId")
                    for e in page.get("elements", [])
                    if e.get("elementType") == "chart"
                ],
            )
            per_page[number] = report
        for item in measured["elements"]:
            number, original_id = identities[item["elementId"]]
            item = copy.deepcopy(item)
            item["elementId"] = original_id
            if item.get("repair"):
                item["repair"]["element"] = original_id
            per_page[number]["elements"].append(item)
            if item["status"] != "passed":
                per_page[number]["status"] = "blocked"
        for number, _ in group:
            report = per_page[number]
            destination = folder / str(number)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "text-fit.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            reports.append(report)
    return reports
