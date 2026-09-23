"""Render a prepared PPTX through local LibreOffice and Poppler."""
from pathlib import Path
import shutil
import subprocess


def run_command(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + ' failed: ' + (result.stdout + result.stderr)[-2000:])


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
    run_command([poppler, '-scale-to', str(width), '-png', str(pdf), str(folder/'page')], folder)
    shutil.rmtree(folder/'office-profile', ignore_errors=True)
    return {'name': 'LibreOffice + pdftoppm', 'maxPixels': width,
            'scope': 'static single-page preview; final merged PPTX and native PowerPoint/WPS unverified'}
