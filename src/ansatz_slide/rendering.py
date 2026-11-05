"""Render a prepared PPTX through local LibreOffice and Poppler."""
from pathlib import Path
import shutil
import subprocess
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile


def run_command(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + ' failed: ' + (result.stdout + result.stderr)[-2000:])


def verify_table_text(source, pdf, folder):
    """Reject missing table text in the actual consumer PDF, not a size test."""
    with ZipFile(source) as archive:
        slides=sorted((n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide[0-9]+\.xml',n)),
                      key=lambda n:int(re.search(r'slide([0-9]+)',n).group(1)))
        for number,name in enumerate(slides,1):
            root=ET.fromstring(archive.read(name))
            texts=[''.join(t.text or '' for t in cell.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
                   for cell in root.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/main}tc')]
            texts=[t for t in texts if t.strip()]
            if not texts:continue
            extractor=shutil.which('pdftotext')
            if not extractor:raise RuntimeError('Table rendering verification requires Poppler pdftotext')
            destination=folder/f'table-text-{number}.txt'
            run_command([extractor,'-f',str(number),'-l',str(number),'-layout',str(pdf),str(destination)],folder)
            normalize=lambda text: ''.join(text.split()).replace('\u00ad','')
            rendered=normalize(destination.read_text(encoding='utf-8'))
            missing=[text for text in texts if normalize(text) not in rendered]
            if missing:
                raise RuntimeError('Rendered table text is missing or changed on page '+str(number)+
                                   '; inspect LibreOffice font/merged-cell compatibility. Evidence: '+str(destination))


def render_pptx(source, folder, width=1600):
    office = shutil.which('soffice') or shutil.which('libreoffice')
    poppler = shutil.which('pdftoppm')
    if not office or not poppler:
        raise RuntimeError('Page check needs LibreOffice (soffice) and Poppler (pdftoppm)')
    profile = (folder/'office-profile').resolve().as_uri()
    run_command([office, '-env:UserInstallation='+profile, '--headless', '--convert-to', 'pdf',
                 '--outdir', str(folder), str(source)], folder)
    pdf = folder/(source.stem+'.pdf')
    if not pdf.is_file():
        raise RuntimeError('Office did not produce a PDF')
    verify_table_text(source,pdf,folder)
    run_command([poppler, '-scale-to', str(width), '-png', str(pdf), str(folder/'page')], folder)
    shutil.rmtree(folder/'office-profile', ignore_errors=True)
    return {'name': 'LibreOffice + pdftoppm', 'maxPixels': width,
            'scope': 'static render of the supplied PPTX; native PowerPoint/WPS unverified'}
