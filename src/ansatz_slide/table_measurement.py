"""Measure consumer-expanded tables, including empty cells, on isolated slides.

Only probe fill colors change. Row heights, text, fonts, merges and borders keep
source semantics. A 144 dpi silhouette exposes table growth before page clipping.
"""
import copy
from pathlib import Path
import shutil
from .package import Package
from .slides import SlideWriter
from .rendering import run_command, verify_table_text


def ink_bounds(path):
    """Read Poppler's binary graymap without an imaging dependency."""
    with Path(path).open('rb') as stream:
        def tokens():
            while True:
                line=stream.readline()
                if not line:raise ValueError('Truncated PGM header')
                if not line.startswith(b'#'):return line.split()
        if tokens()!=[b'P5']:raise ValueError('Expected binary graymap')
        width,height=map(int,tokens())
        if tokens()!=[b'255']:raise ValueError('Expected 8-bit graymap')
        left,top,right,bottom=width,height,-1,-1
        for y in range(height):
            row=stream.read(width)
            if len(row)!=width:raise ValueError('Truncated graymap')
            pixels=[x for x,value in enumerate(row) if value<240]
            if pixels:
                left=min(left,pixels[0]);right=max(right,pixels[-1]+1)
                top=min(top,y);bottom=y+1
    return None if right<0 else [left/2,top/2,right/2,bottom/2]


def check_tables(elements,theme,folder):
    if not elements:return []
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    office=shutil.which('soffice') or shutil.which('libreoffice')
    raster=shutil.which('pdftoppm')
    if not office or not raster:raise RuntimeError('Table measurement requires LibreOffice and Poppler')
    margin=72
    width=max(1000,max(e['bounds'][2] for e in elements)+2*margin)
    height=max(4000,max(e['bounds'][3] for e in elements)+2*margin)
    if max(width,height)>10000:raise ValueError('Table measurement probe too large; split the table')
    package=Package()
    for number,element in enumerate(elements,1):
        candidate=copy.deepcopy(element)
        candidate['bounds'][:2]=[margin,margin]
        candidate.pop('rotation',None);candidate.pop('animations',None)
        for row in candidate['rows']:
            for cell in row:cell['fill']={'type':'solid','color':'#000000'}
        SlideWriter(package,number,theme or {},{},[width,height],{'effect':'none','speed':'fast'}).write({'elements':[candidate]})
    source=folder/'table-probe.pptx';source.write_bytes(package.finish([width,height],len(elements)))
    profile=folder/'office-profile'
    try:
        run_command([office,'-env:UserInstallation='+profile.resolve().as_uri(),'--headless','--convert-to','pdf','--outdir',str(folder.resolve()),str(source.resolve())],folder)
        pdf=folder/'table-probe.pdf'
        verify_table_text(source,pdf,folder)
        reports=[]
        for number,element in enumerate(elements,1):
            prefix=folder/f'table-{number}'
            run_command([raster,'-f',str(number),'-l',str(number),'-singlefile','-r','144','-gray',str(pdf.resolve()),str(prefix.resolve())],folder)
            bounds=ink_bounds(prefix.with_suffix('.pgm'))
            item={'elementId':element['elementId'],'bounds':element['bounds'],'status':'unverified',
                  'scope':'Isolated consumer table silhouette, including cell fills and text; 0.5 pt raster resolution. Glyph appearance and PowerPoint/WPS remain unverified.',
                  'evidence':str(prefix.with_suffix('.pgm'))}
            if bounds is None:item['reason']='Renderer produced no table silhouette'
            else:
                left,top,right,bottom=[v-margin for v in bounds];w,h=element['bounds'][2:]
                item.update(measuredBounds=[left,top,right-left,bottom-top],requiredWidth=right,requiredHeight=bottom)
                if bounds[2]>=width-1 or bounds[3]>=height-1:item['reason']='Probe limit reached; table may be clipped; split before retrying'
                else:
                    edges={key:round(value,2) for key,value in [('left',-left),('top',-top),('right',right-w),('bottom',bottom-h)] if value>1}
                    if edges:item.update(status='overflow',overflowEdges=edges,reason=f'Renderer expands table beyond declared bounds: {edges}',repairHint='Enlarge the table bounds to the measured extent and reposition neighbors, or split rows while preserving content. No universal minimum row height is assumed.')
                    else:item['status']='passed'
            reports.append(item)
        return reports
    finally:shutil.rmtree(profile,ignore_errors=True)
