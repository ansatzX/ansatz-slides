"""Optional, deliberately bounded YAML DSL -> Deckcraft JSON command adapter."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .images import image_info
from .validation import ValidationError


def _keys(value, allowed, where):
    extra=set(value)-set(allowed)
    if extra:
        raise ValidationError(f'Deckcraft backend: unsupported {where} fields: {", ".join(sorted(extra))}')


def _color(value):
    if not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):
        raise ValidationError('Deckcraft backend requires explicit #RRGGBB colors')
    return value


def _fill(value):
    if value is None:return {'none':True}
    if isinstance(value,str):return {'color':_color(value)}
    _keys(value,('type','color'),'fill')
    if value.get('type')!='solid':raise ValidationError('Deckcraft backend supports solid fills only')
    return {'color':_color(value['color'])}


def commands_for(presentation, images, folder, transition):
    """Compile without IO; images=None checks DSL fields before resource loading."""
    _keys(presentation,('version','title','size','pages','theme','pptdFileName'),'manifest')
    if presentation.get('theme'):
        raise ValidationError('Deckcraft backend requires explicit styles; theme mapping is not supported yet')
    commands=[]
    def add(command_id,**params):commands.append(command_id+'='+json.dumps(params,ensure_ascii=False))
    add('file.new',blank=True,size=presentation['size'])
    if presentation.get('title'):add('file.properties',title=presentation['title'])
    assets=[]
    for number,page in enumerate(presentation['pages'],1):
        _keys(page,('pagePath','pageType','notes','background','elements','allowedOverlaps'),f'page {number}')
        add('slide.new',layout='blank')
        add('design.background',**_fill(page.get('background',{'type':'solid','color':'#FFFFFF'})))
        add('transition.set',kind=transition)
        if page.get('notes'):add('slide.notes',text=page['notes'])
        for element in page['elements']:
            kind=element['elementType'];where=f'page {number} element {element["elementId"]}'
            shared={'elementId','elementType','bounds'}
            if kind=='text':
                _keys(element,shared|{'content'},where)
                c=element['content']
                _keys(c,('text','fontFamily','fontSize','color','bold','italic','align','wrap','backgroundColor'),where+' content')
                text=c.get('text','')
                if re.search(r'<|&|\\\(',text):
                    raise ValidationError(f'Deckcraft backend: {where} needs plain text (no HTML/entities/native math)')
                family=c.get('fontFamily','MiSans')
                if not isinstance(family,str):
                    raise ValidationError(f'Deckcraft backend: {where} requires one fontFamily string; script-specific fonts are not supported')
                align=c.get('align','left');horizontal=align[0] if isinstance(align,list) else align
                vertical=align[1] if isinstance(align,list) and len(align)>1 else 'top'
                add('insert.textBox',rect=element['bounds'],text=text)
                add('shape.fill',**_fill(c.get('backgroundColor')))
                add('shape.line',none=True)
                add('format.font',family=family)
                add('format.size',size=c.get('fontSize',16))
                add('format.color',color=_color(c.get('color','#333333')))
                add('format.bold',on=c.get('bold',False));add('format.italic',on=c.get('italic',False))
                add('format.align',align=horizontal);add('format.anchor',anchor=vertical)
                add('format.margins',left=0,right=0,top=0,bottom=0)
                add('format.wrap',on=c.get('wrap',True));add('format.autofit',mode='none')
            elif kind=='shape':
                _keys(element,shared|{'shapeName','fill','border','rotation'},where)
                preset=element.get('shapeName','rect')
                if preset not in ('rect','roundRect','ellipse','triangle','rightArrow'):
                    raise ValidationError(f'Deckcraft backend: unsupported shape {preset}')
                add('shape.insert',preset=preset,rect=element['bounds'])
                add('shape.fill',**_fill(element.get('fill')))
                border=element.get('border')
                if border:
                    _keys(border,('color','width','style'),where+' border')
                    if border.get('style','solid')!='solid':raise ValidationError('Deckcraft backend supports solid borders only')
                    add('shape.line',color=_color(border.get('color','#000000')),width=border.get('width',1))
                else:add('shape.line',none=True)
                if element.get('rotation'):add('shape.rotate',deg=element['rotation'])
            elif kind=='image':
                _keys(element,shared|{'src','fit'},where)
                fit=element.get('fit',{'mode':'cover'});_keys(fit,('mode',),where+' fit')
                if fit.get('mode')!='contain':
                    raise ValidationError(f'Deckcraft backend: {where} requires explicit fit.mode=contain')
                if images is None:
                    continue  # Source-only capability check, before asset IO.
                data=images[element['src']];ext,w,h=image_info(data)
                if ext not in ('png','jpg'):raise ValidationError('Deckcraft backend supports PNG/JPEG images only')
                x,y,bw,bh=element['bounds'];scale=min(bw/w,bh/h)
                rect=[x+(bw-w*scale)/2,y+(bh-h*scale)/2,w*scale,h*scale]
                asset=folder/f'asset-{len(assets)}.{ext}';assets.append((asset,data))
                add('insert.picture',path=str(asset),rect=rect)
            else:raise ValidationError(f'Deckcraft backend: unsupported {where} type {kind}')
            add('shape.rename',name=element['elementId'])
    return commands,assets


def check_source(presentation, transition='none'):
    """Reject unsupported DSL before asset IO, Office or backend execution."""
    commands_for(presentation, None, Path('.'), transition)


def export_bytes(presentation,images,folder,transition='none'):
    with tempfile.TemporaryDirectory(prefix='deckcraft-',dir=folder) as scratch:
        stage=Path(scratch).resolve()
        commands,assets=commands_for(presentation,images,stage,transition)
        executable=shutil.which('deckcraft-cli')
        if not executable:raise RuntimeError('Deckcraft backend requires deckcraft-cli on PATH')
        for path,data in assets:path.write_bytes(data)
        output=stage/'candidate.pptx'
        args=[executable,'run']
        for command in commands:args.extend(['--cmd',command])
        args.extend(['--save',str(output)])
        result=subprocess.run(args,cwd=stage,capture_output=True,text=True,timeout=120)
        if result.returncode or not output.is_file():
            raise RuntimeError('Deckcraft creation failed: '+(result.stdout+result.stderr)[-2000:])
        return output.read_bytes()
