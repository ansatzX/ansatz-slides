"""Inspect OOXML and render actual exported PPTX files. Not a visual-approval oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch',type=Path,required=True,help='A directory under the repository tmp/')
    args=parser.parse_args()
    scratch=args.scratch.resolve()
    if 'tmp' not in scratch.parts or str(scratch).startswith(('/tmp/','/private/tmp/')):
        parser.error('Use a repository-local tmp directory, never system /tmp')
    scratch.mkdir(parents=True,exist_ok=True)
    for binary in ('soffice','pdftoppm','pdftotext'):
        if not shutil.which(binary):parser.error(f'Missing {binary}; install locally/manually before QA')
    env=dict(os.environ,TMPDIR=str(scratch),XDG_CACHE_HOME=str(scratch/'cache'))
    reports=[]
    for ident in json.loads((HERE/'projects.json').read_text()):
        project=HERE/ident
        deck=project/'demo.pptx'
        page=json.loads((project/'pages/01.page').read_text())
        with zipfile.ZipFile(deck) as z:
            assert z.testzip() is None
            slides=[n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]
            assert len(slides)==1,slides
            xml=ET.fromstring(z.read(slides[0]))
            assert len(xml.findall('.//p:pic',NS))==1
            assert not xml.findall('.//p:graphicFrame',NS),'Unexpected native table/chart'
            assert len(xml.findall('p:transition',NS))==1
            assert xml.find('p:transition/p:fade',NS) is not None
            native_text=xml.findall('.//a:t',NS)
            expected=[el for el in page['elements'] if el['elementType']=='text']
            assert len(native_text)>=len(expected),(len(native_text),len(expected))
            asset=(project/'media/evidence.png').read_bytes()
            assert any(z.read(n)==asset for n in z.namelist() if n.startswith('ppt/media/')),'Source image changed'
            for el in page['elements']:
                x,y,w,h=el['bounds']
                assert x>=0 and y>=0 and x+w<=960 and y+h<=540,el['elementId']
                if el['elementType']=='image':assert w<960 and h<540,'Whole-slide screenshot'
            report={'project':ident,'zip_integrity':'passed','slides':1,'external_images':1,
                    'native_text_runs':len(native_text),'native_charts_or_tables':0,
                    'source_image_preserved':True,'bounds':'passed','root_fade':'passed',
                    'pptx_sha256':hashlib.sha256(deck.read_bytes()).hexdigest(),
                    'visual_review':'Requires human/agent inspection of preview.png; not inferred by this script'}
        out=scratch/ident;out.mkdir(exist_ok=True)
        subprocess.run(['soffice',f'-env:UserInstallation={(scratch/"lo-profile").as_uri()}','--headless','--convert-to','pdf','--outdir',str(out),str(deck)],check=True,env=env,timeout=60)
        pdf=out/'demo.pdf'
        assert pdf.is_file() and pdf.stat().st_size>0
        subprocess.run(['pdftoppm','-png','-singlefile','-scale-to','1440',str(pdf),str(project/'preview')],check=True,env=env,timeout=60)
        subprocess.run(['pdftotext','-layout',str(pdf),str(out/'rendered-text.txt')],check=True,env=env,timeout=60)
        report['render_engine']='LibreOffice PDF -> Poppler PNG, 1440px'
        report['preview_sha256']=hashlib.sha256((project/'preview.png').read_bytes()).hexdigest()
        reports.append(report)
        print(ident,'OOXML + render passed',flush=True)
    (HERE/'verification.json').write_text(json.dumps(reports,indent=2)+'\n')


if __name__=='__main__':main()
