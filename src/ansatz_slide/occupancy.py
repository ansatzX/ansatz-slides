"""Renderer-free rectangular occupancy precheck in canvas coordinates."""
from array import array
import gzip
import json
import math
from pathlib import Path
import struct
import zlib


class GeometryError(ValueError):
    """A fresh geometry check rejected publication or rendering."""


def overlap_declarations(page):
    """Validate explicit pair-wise intent even for direct in-memory callers."""
    declarations=page.get('allowedOverlaps',[])
    if not isinstance(declarations,list):raise GeometryError('allowedOverlaps must be a list')
    ids={e['elementId'] for e in page.get('elements',[])}
    allowed={}
    for item in declarations:
        if not isinstance(item,dict) or set(item)!={'elements','reason'}:
            raise GeometryError('Each allowedOverlaps entry requires only elements and reason')
        pair=item['elements'];reason=item['reason']
        if (not isinstance(pair,list) or len(pair)!=2 or
            not all(isinstance(v,str) and v in ids for v in pair) or pair[0]==pair[1]):
            raise GeometryError('allowedOverlaps requires two different existing element IDs')
        if not isinstance(reason,str) or not reason.strip():
            raise GeometryError('allowedOverlaps requires a nonempty reason')
        key=tuple(sorted(pair))
        if key in allowed:raise GeometryError('Duplicate allowedOverlaps pair')
        allowed[key]=reason
    return allowed


def require_pass(report, label='page'):
    if report['status']=='passed':return report
    details=[]
    if report['unapprovedOverlaps']:
        details.append('undeclared overlaps '+', '.join('/'.join(p['elements']) for p in report['unapprovedOverlaps'][:8]))
    if report['outOfBounds']:
        details.append('out of bounds '+', '.join(p['elementId'] for p in report['outOfBounds'][:8]))
    if report['invalidDegenerateBounds']:
        details.append('zero-area elements '+', '.join(report['invalidDegenerateBounds'][:8]))
    raise GeometryError(f'Geometry precheck failed ({label}): '+ '; '.join(details)+
                        '. Fix bounds or declare intentional overlap pairs with reasons; use page check-overlap for diagnostics.')


def require_pages(size, pages):
    """Recompute from current in-memory inputs; no receipt or skip flag is trusted."""
    reports=[]
    for number,page in enumerate(pages,1):
        report,_=analyze(size,page,max(1,max(size)/2000))
        require_pass(report,f'page {number}')
        reports.append(report)
    return reports


def png_gray(width, height, pixels):
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows = b''.join(b'\0'+pixels[y*width:(y+1)*width] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0))+
            chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def envelope(element):
    x,y,w,h=element['bounds']
    angle=math.radians(element.get('rotation',0))
    cosine,sine=math.cos(angle),math.sin(angle)
    if abs(cosine)<1e-12:cosine=0
    if abs(sine)<1e-12:sine=0
    rw=abs(w*cosine)+abs(h*sine)
    rh=abs(w*sine)+abs(h*cosine)
    return [x+(w-rw)/2,y+(h-rh)/2,rw,rh]


def analyze(size, page, cell_size=1):
    if not math.isfinite(cell_size) or cell_size<=0:
        raise ValueError('cell-size must be finite and positive')
    width,height=size
    if any(not math.isfinite(v) or v<=0 for v in size):
        raise GeometryError('Canvas dimensions must be finite and positive')
    allowed=overlap_declarations(page)
    cols,rows=math.ceil(width/cell_size),math.ceil(height/cell_size)
    if cols*rows>4_000_000:
        raise ValueError('Occupancy grid exceeds 4000000 cells; increase --cell-size')
    stride=cols+1
    diff=array('i',[0])*((rows+1)*stride)
    boxes=[];outside=[];degenerate=[]
    for e in page.get('elements',[]):
        bounds=e.get('bounds')
        if (not isinstance(bounds,(list,tuple)) or len(bounds)!=4 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in bounds) or
            bounds[2]<0 or bounds[3]<0):
            raise GeometryError('Element bounds must contain four finite numbers with nonnegative sizes')
        rotation=e.get('rotation',0)
        if type(rotation) not in (int,float) or not math.isfinite(rotation):
            raise GeometryError('Element rotation must be finite')
        x,y,w,h=envelope(e);right=x+w;bottom=y+h
        item={'elementId':e['elementId'],'elementType':e['elementType'],
              'bounds':e['bounds'],'envelope':[x,y,w,h]}
        if e.get('rotation',0):item['rotation']=e['rotation']
        boxes.append(item)
        if x<0 or y<0 or right>width or bottom>height:outside.append(item)
        if w<=0 or h<=0:
            degenerate.append(e['elementId']);continue
        x0=max(0,min(cols,math.floor(x/cell_size)))
        y0=max(0,min(rows,math.floor(y/cell_size)))
        x1=max(0,min(cols,math.ceil(right/cell_size)))
        y1=max(0,min(rows,math.ceil(bottom/cell_size)))
        if x1<=x0 or y1<=y0:continue
        diff[y0*stride+x0]+=1;diff[y0*stride+x1]-=1
        diff[y1*stride+x0]-=1;diff[y1*stride+x1]+=1
    counts=array('I',[0])*(rows*cols)
    for y in range(rows):
        across=0
        for x in range(cols):
            idx=y*stride+x;across+=diff[idx]
            diff[idx]=across+(diff[idx-stride] if y else 0)
            counts[y*cols+x]=diff[idx]
    overlaps=[]
    for i,a in enumerate(boxes):
        ax,ay,aw,ah=a['envelope']
        for b in boxes[i+1:]:
            bx,by,bw,bh=b['envelope']
            x0=max(0,ax,bx);y0=max(0,ay,by)
            x1=min(width,ax+aw,bx+bw);y1=min(height,ay+ah,by+bh)
            if x1>x0 and y1>y0:
                overlaps.append({'elements':[a['elementId'],b['elementId']],
                                 'intersection':[x0,y0,x1-x0,y1-y0],
                                 'area':(x1-x0)*(y1-y0)})
    unapproved=[];approved=[]
    for overlap in overlaps:
        reason=allowed.get(tuple(sorted(overlap['elements'])))
        if reason is None:unapproved.append(overlap)
        else:approved.append({**overlap,'reason':reason})
    invalid_degenerate=[e['elementId'] for e in boxes if e['elementId'] in degenerate and e['elementType']!='line']
    report={'canvas':size,'cellSize':cell_size,'matrixShape':[rows,cols],
            'matrixIndex':'matrix[row=y][column=x]; origin at top left',
            'elementCount':len(boxes),'elements':boxes,'overlaps':overlaps,
            'outOfBounds':outside,'degenerateBounds':degenerate,
            'status':'blocked' if unapproved or outside or invalid_degenerate else 'passed',
            'unapprovedOverlaps':unapproved,'approvedOverlaps':approved,
            'invalidDegenerateBounds':invalid_degenerate,
            'occupiedCells':sum(v>0 for v in counts),'overlapCells':sum(v>1 for v in counts),
            'maxOccupancy':max(counts,default=0),
            'interpretation':'Mandatory geometry gate: no out-of-bounds elements or undeclared positive-area overlaps. Intentional overlap requires an explicit pair and reason; passing is not visual acceptance.',
            'limits':'Uses rectangular envelopes, conservatively enlarged for rotation. Does not measure glyph ink, image transparency, stroke width, shadows or text overflow. Zero-area bounds are listed separately. Fractional boundaries can share raster cells without positive geometric intersection.'}
    return report,counts


def write_precheck(size,page,folder,cell_size=1):
    folder=Path(folder)
    report,counts=analyze(size,page,cell_size)
    rows,cols=report['matrixShape']
    # Folder is owned by the caller (fresh output or private preview stage).
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'occupancy.png').write_bytes(png_gray(cols,rows,bytes(0 if n else 255 for n in counts)))
    levels={0:255,1:192,2:96}
    (folder/'overlap.png').write_bytes(png_gray(cols,rows,bytes(levels.get(n,0) for n in counts)))
    for name,binary in [('occupancy.tsv.gz',True),('counts.tsv.gz',False)]:
        with gzip.open(folder/name,'wt',encoding='utf-8',newline='\n') as stream:
            for y in range(rows):
                stream.write('\t'.join(str(int(v>0) if binary else v) for v in counts[y*cols:(y+1)*cols])+'\n')
    report['files']={key:str((folder/name).absolute()) for key,name in
                     [('occupancyImage','occupancy.png'),('overlapImage','overlap.png'),
                      ('occupancyMatrix','occupancy.tsv.gz'),('countMatrix','counts.tsv.gz')]}
    report['grayscaleLegend']={'occupancy':'0=black occupied, 255=white empty',
                              'overlap':'255=empty, 192=one element, 96=two, 0=three or more'}
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def matrix_payload(report):
    """Return both exact matrices as repeated RLE rows, plus bounded conflict crops."""
    with gzip.open(report['files']['countMatrix'],'rt',encoding='utf-8') as stream:
        rows=[[int(v) for v in line.split()] for line in stream]
    def encode(binary):
        bands=[]
        for y,row in enumerate(rows):
            runs=[]
            for value in row:
                value=int(value>0) if binary else value
                if runs and runs[-1][0]==value:runs[-1][1]+=1
                else:runs.append([value,1])
            if bands and bands[-1]['runs']==runs:bands[-1]['rowCount']+=1
            else:bands.append({'startRow':y,'rowCount':1,'runs':runs})
        return bands
    regions=[];cell=report['cellSize'];height,width=report['matrixShape']
    for pair in report['unapprovedOverlaps']:
        x,y,w,h=pair['intersection']
        x0=max(0,math.floor(x/cell));y0=max(0,math.floor(y/cell))
        x1=min(width,math.ceil((x+w)/cell));y1=min(height,math.ceil((y+h)/cell))
        regions.append({'elements':pair['elements'],'originCell':[x0,y0],
                        'fullShape':[y1-y0,x1-x0],'sampleShape':[min(32,y1-y0),min(32,x1-x0)],
                        'truncated':y1-y0>32 or x1-x0>32,
                        'counts':[r[x0:min(x1,x0+32)] for r in rows[y0:min(y1,y0+32)]]})
    return {'encoding':'row-bands-rle-v1','shape':report['matrixShape'],'cellSize':cell,
            'origin':[0,0],'index':'matrix[y][x]',
            'decode':'For each band, repeat its row rowCount times. Each [value,length] run repeats value length times. No cells are omitted.',
            'counts':encode(False),'occupancy':encode(True),'conflictRegions':regions}
