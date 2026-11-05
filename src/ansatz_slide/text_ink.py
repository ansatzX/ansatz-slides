"""Resolve PDF font-metric overshoot using rasterized ink, only when safe.

Poppler word boxes describe font metrics, not painted pixels. This probe uses
existing text-probe bytes and never changes authored text or font settings.
"""
import re
import shutil
from pathlib import Path
from .rendering import run_command


def bounds(pdf, number, folder, measured, frame, *, margin=72):
    tool=shutil.which('pdftoppm')
    if not tool:return None
    left,top,width,height=measured
    x0=max(0,margin+min(0,left)-8);y0=max(0,margin+min(0,top)-8)
    x1=margin+max(frame[0],left+width)+8;y1=margin+max(frame[1],top+height)+8
    scale=2;w=int((x1-x0)*scale)+2;h=int((y1-y0)*scale)+2
    if w*h>12_000_000:return None
    prefix=(Path(folder)/f'ink-{number}').resolve()
    run_command([tool,'-f',str(number),'-l',str(number),'-r','144','-x',str(int(x0*scale)),
                 '-y',str(int(y0*scale)),'-W',str(w),'-H',str(h),'-gray','-singlefile',str(pdf),str(prefix)],folder)
    data=prefix.with_suffix('.pgm').read_bytes()
    match=re.match(rb'P5\s+(?:#[^\n]*\n\s*)?(\d+)\s+(\d+)\s+255\s',data)
    if not match:return None
    w,h=map(int,match.groups());pixels=data[match.end():]
    if len(pixels)!=w*h:return None
    xmin=w;ymin=h;xmax=ymax=-1
    for y in range(h):
        row=pixels[y*w:(y+1)*w]
        dark=[x for x,value in enumerate(row) if value<245]
        if dark:xmin=min(xmin,dark[0]);xmax=max(xmax,dark[-1]);ymin=min(ymin,y);ymax=y
    if xmax<0:return None
    return [int(x0*scale)/scale+xmin/scale-margin,
            int(y0*scale)/scale+ymin/scale-margin,
            (xmax-xmin+1)/scale,(ymax-ymin+1)/scale]
