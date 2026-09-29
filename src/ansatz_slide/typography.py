"""Measure native text using the same LibreOffice engine as page previews.

Probe slides retain text width, runs, fonts and paragraph rules but remove the
height constraint. PDF word extents expose occupied space before clipping.
"""
import copy
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from .package import Package
from .slides import SlideWriter
from .rendering import run_command
from .richtext import RichTextParser


class TextFitError(ValueError):
    def __init__(self, report):
        self.report = report
        details = '; '.join(f"{e['elementId']}: {e.get('reason', e['status'])}" for e in report['elements'] if e['status'] != 'passed')
        super().__init__('Text fit check failed: '+details)


def check_page(size, page, theme, folder):
    """Return measured text bounds; never silently equate box size with text size."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    report={'status':'passed','engine':'LibreOffice + Poppler pdftotext',
            'units':'pt (same as source coordinates)','elements':[],
            'unmeasuredObjects':[e.get('elementId') for e in page.get('elements',[]) if e.get('elementType') in ('table','chart')],
            'scope':'Native text elements; table/chart internal labels are not measured by this check. Target PowerPoint/WPS layout may differ.'}
    entries=[]
    for element in page.get('elements',[]):
        if element.get('elementType')!='text':continue
        content=element.get('content',{})
        parser=RichTextParser();parser.feed(str(content.get('text','')));parser.close()
        text=''.join(run.value for para in parser.paragraphs for run in para.runs)
        if not text.strip():continue
        item={'elementId':element['elementId'],'bounds':element['bounds'],
              'status':'unverified','requestedStyles':[], 'wrap':content.get('wrap',True)}
        base={'fontFamily':'MiSans','fontSize':16,'lineHeight':1.2,'bold':False,'italic':False,
              **(theme or {}).get('textStyles',{}).get((content.get('style') or '').lstrip('$'),{}),**content}
        for para in parser.paragraphs:
            for run in para.runs:
                style={**base,**para.style,**run.style}
                item['requestedStyles'].append({k:style.get(k) for k in
                    ('fontFamily','fontSize','bold','italic','lineHeight','lineHeightPx','letterSpacing','marginTop')})
        report['elements'].append(item)
        if content.get('textDirection')=='vertical':
            item['reason']='Vertical text requires a dedicated measurement layout; not treated as fitting'
        else:entries.append((element,item))
    if not entries:
        report['status']='blocked' if any(e['status']!='passed' for e in report['elements']) else 'passed'
        (folder/'text-fit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        return report
    office=shutil.which('soffice') or shutil.which('libreoffice')
    extractor=shutil.which('pdftotext');fonts=shutil.which('pdffonts')
    if not office or not extractor or not fonts:
        raise RuntimeError('Text measurement requires LibreOffice and Poppler (pdftotext, pdffonts)')
    margin=72.0
    # Extra horizontal space reveals unwrapped overflow. Extra vertical space
    # reveals lines that the original frame would clip. Guard probe limits.
    probe_width=max(2000.0,max(e['bounds'][2] for e,_ in entries)+2*margin)
    probe_height=max(4000.0,max(e['bounds'][3] for e,_ in entries)+2*margin)
    if max(probe_width,probe_height)>10000:
        raise RuntimeError('Text measurement probe exceeds supported size; split the page before measuring')
    package=Package()
    aligned_probes={}
    for number,(element,item) in enumerate(entries,1):
        candidate=copy.deepcopy(element);candidate['bounds']=[margin,margin,element['bounds'][2],probe_height-2*margin]
        candidate.pop('animations',None)
        candidate.pop('rotation',None)  # Measure in the textbox's local coordinates.
        align=candidate['content'].get('align','left')
        candidate['content']['align']=[align[0] if isinstance(align,list) else align,'top']
        # Internal probe serialization intentionally has no publication path.
        SlideWriter(package,number,theme or {},{},[probe_width,probe_height],{'effect':'none','speed':'fast'}).write({'elements':[candidate]})
    # The tall, top-aligned probe reveals hidden lines, but its origin is not
    # the origin of centered/bottom-aligned text in the actual frame. Measure
    # those frames too, in the same Office conversion rather than guessing an
    # alignment offset from font metrics.
    for index,(element,item) in enumerate(entries):
        align=element['content'].get('align')
        if isinstance(align,list) and len(align)>1 and align[1] in ('middle','bottom'):
            number=len(entries)+len(aligned_probes)+1
            aligned_probes[index]=number-1
            candidate=copy.deepcopy(element)
            candidate['bounds'][:2]=[margin,margin]
            candidate.pop('animations',None);candidate.pop('rotation',None)
            SlideWriter(package,number,theme or {},{},[probe_width,probe_height],{'effect':'none','speed':'fast'}).write({'elements':[candidate]})
    source=folder/'text-probe.pptx';source.write_bytes(package.finish([probe_width,probe_height],len(entries)+len(aligned_probes)))
    profile=(folder/'text-office-profile').resolve()
    try:
        run_command([office,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf','--outdir',str(folder.resolve()),str(source.resolve())],folder)
        pdf=folder/'text-probe.pdf';bbox=folder/'text-bounds.html'
        if not pdf.is_file():raise RuntimeError('Text measurement did not produce a PDF')
        run_command([extractor,'-bbox','-enc','UTF-8',str(pdf.resolve()),str(bbox.resolve())],folder)
        pages=ET.parse(bbox).getroot().findall('.//{*}page')
        if len(pages)!=len(entries)+len(aligned_probes):raise RuntimeError('Text measurement page count mismatch')
        import subprocess
        for number,((element,item),pdfpage) in enumerate(zip(entries,pages),1):
            result=subprocess.run([fonts,'-f',str(number),'-l',str(number),str(pdf.resolve())],capture_output=True,text=True,timeout=60)
            if result.returncode:raise RuntimeError('Could not inspect fonts used for text measurement')
            item['renderedFonts']=[line.split()[0] for line in result.stdout.splitlines()[2:] if line.strip()]
            words=pdfpage.findall('.//{*}word')
            if not words:
                item['reason']='Renderer produced no measurable text; glyphs or font extraction may be missing';continue
            left=min(float(w.attrib['xMin']) for w in words)-margin
            top=min(float(w.attrib['yMin']) for w in words)-margin
            right=max(float(w.attrib['xMax']) for w in words)-margin
            bottom=max(float(w.attrib['yMax']) for w in words)-margin
            intrinsic_height=bottom-top
            if number-1 in aligned_probes:
                item['unrestrictedBounds']=[left,top,right-left,intrinsic_height]
                actual_words=pages[aligned_probes[number-1]].findall('.//{*}word')
                if [w.text for w in actual_words]!=[w.text for w in words]:
                    item['reason']='Original aligned frame clipped or changed measured text; enlarge the frame';continue
                left=min(float(w.attrib['xMin']) for w in actual_words)-margin
                top=min(float(w.attrib['yMin']) for w in actual_words)-margin
                right=max(float(w.attrib['xMax']) for w in actual_words)-margin
                bottom=max(float(w.attrib['yMax']) for w in actual_words)-margin
                item['alignmentMeasured']=element['content']['align'][1]
            item.update(measuredBounds=[left,top,right-left,bottom-top],
                        requiredWidth=max(0,right)-min(0,left),requiredHeight=max(0,bottom)-min(0,top),
                        wordCount=len(words))
            w,h=element['bounds'][2:]
            tolerance=0.5  # PDF coordinate/font rounding in source point units.
            if right>=probe_width-2*margin-tolerance or bottom>=probe_height-2*margin-tolerance:
                item['reason']='Text reaches the probe limit; measurement may be clipped'
            elif left < -tolerance or top < -tolerance or right>w+tolerance or bottom>h+tolerance or intrinsic_height>h+tolerance:
                overflow={edge:round(amount,4) for edge,amount in
                          [('left',-left),('top',-top),('right',right-w),('bottom',bottom-h)] if amount>tolerance}
                if intrinsic_height>h+tolerance:overflow['height']=round(intrinsic_height-h,4)
                detail=', '.join(f'{edge} {amount:.2f} pt' for edge,amount in overflow.items())
                hint=('Top/left overflow is a local text-origin/line-metric issue; enlarging frame width/height alone does not fix it. Inspect font and paragraph spacing.'
                      if 'top' in overflow or 'left' in overflow else 'Adjust wrapping, frame dimensions or typography while preserving content.')
                item.update(status='overflow',overflowEdges=overflow,repairHint=hint,
                            reason=f"overflows {detail}; local bounds [{left:.2f}, {top:.2f}, {right:.2f}, {bottom:.2f}]; frame {w} × {h} pt. {hint}")
            else:item['status']='passed'
    finally:
        shutil.rmtree(profile,ignore_errors=True)
    report['status']='blocked' if any(e['status']!='passed' for e in report['elements']) else 'passed'
    (folder/'text-fit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    return report


def require_pass(report):
    if report['status']!='passed':raise TextFitError(report)
    return report


def check_project(project, number, output):
    from .page_api import snapshot, unchanged
    snap=snapshot(project)
    if not 1<=number<=len(snap['pages']):raise ValueError('Page out of range')
    folder=Path(output).absolute()
    folder.mkdir(parents=True,exist_ok=False)
    report=check_page(snap['manifest']['size'],snap['pages'][number-1],snap['manifest'].get('theme',{}),folder)
    if not unchanged(snap['tracked']):raise RuntimeError('Source changed during text measurement; retry')
    return report


def check_loaded(pptd, root):
    """Measure exactly the in-memory text which will be serialized by this export."""
    from .page_api import session_path
    import tempfile
    root=session_path(Path(root)/'.ansatz');root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='text-check-',dir=root) as folder:
        for number,page in enumerate(pptd['pages'],1):
            report=check_page(pptd['size'],page,pptd.get('theme',{}),Path(folder)/str(number))
            report['page']=number
            require_pass(report)
    return {'status':'passed','pageCount':len(pptd['pages']),'engine':'LibreOffice + Poppler',
            'scope':'Native horizontal text elements; other text-bearing object types need separate review'}
