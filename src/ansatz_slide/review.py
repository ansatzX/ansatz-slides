"""One version-bound, local review manifest and a static page viewer."""

import copy
import json
from pathlib import Path

from . import page_api as api
from .project import atomic_write


def write(
    folder,
    snap,
    pages,
    images,
    issues,
    *,
    changed=(),
    checks=None,
    pptx=None,
    delivered=False,
    source_preflight=None,
):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checks = checks or {}
    rows = []
    for n, page in enumerate(pages, 1):
        rows.append(
            {
                "page": n,
                "source": str(snap["paths"][n - 1]),
                "title": api.title(page),
                "image": str(Path(images[n - 1]).relative_to(folder))
                if n <= len(images)
                else None,
                "changed": n in changed,
                "checks": checks.get(n, {"geometry": "not_run", "text": "not_run"}),
                "visual": {"status": "not_reviewed", "note": ""},
                "issues": [
                    copy.deepcopy(i) for i in issues if i.get("page") in (None, n)
                ],
                "sourceIssues": [
                    copy.deepcopy(i)
                    for i in (source_preflight or {}).get("issues", [])
                    if i.get("page") in (None, n)
                ],
            }
        )
    if pptx is not None and not Path(pptx).is_file():
        pptx = None
    data = {
        "format": "slide-review-v1",
        "kind": "delivery" if delivered else "candidate",
        "pptx": str(pptx) if pptx else None,
        "pptxHash": api.sha(Path(pptx).read_bytes()) if pptx else None,
        "tracked": dict(snap["tracked"]),
        "pages": rows,
        "meaning": "Program checks and rendered images do not constitute visual or scientific acceptance.",
    }
    save(folder, data)
    return {
        "manifest": str(folder / "review.json"),
        "viewer": str(folder / "index.html"),
        "kind": data["kind"],
        "visual": "not_reviewed",
    }


def save(folder, data):
    folder = Path(folder)
    atomic_write(folder / "review.json", api.json_bytes(data), force=True)
    # JSON is data, never executable markup from titles/notes/paths.
    embedded = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    document = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>PPTX 页面审阅</title>
<style>body{margin:0;font:16px sans-serif;background:#eee;color:#222}header{padding:12px;background:#fff;position:sticky;top:0}main{display:grid;grid-template-columns:200px 1fr;gap:18px;padding:18px;height:calc(100vh - 70px);box-sizing:border-box}nav,article{overflow:auto}nav button{display:block;width:100%;margin-bottom:10px;text-align:left;border:1px solid #aaa;padding:8px;background:white;cursor:pointer}nav img{width:100%}#page{width:100%;max-height:calc(100vh - 220px);object-fit:contain;background:white}#source{overflow-wrap:anywhere}article{min-width:0}#issues{white-space:pre-wrap;background:#fff;padding:12px}button{padding:8px}#state{margin-left:20px}</style>
<header><button id="prev">上一页</button> <button id="next">下一页</button><span id="state"></span>
<label>显示 <select id="filter"><option value="all">全部页面</option><option value="changed">修改页面</option><option value="issues">有问题的页面</option></select></label></header>
<main><nav id="list"></nav><article><h2 id="title"></h2><img id="page"><p id="source"></p><div id="issues"></div></article></main>
<script>const data=__DATA__;let selected=0;const el=id=>document.getElementById(id);
function hasIssues(p){return p.issues.length||(p.sourceIssues||[]).length||p.visual.status==='needs_fix';}
function show(i){if(!data.pages.length)return;selected=(i+data.pages.length)%data.pages.length;const p=data.pages[selected];el('title').textContent=p.page+' · '+p.title;el('page').hidden=!p.image;if(p.image)el('page').src=p.image;el('source').textContent=p.source;el('state').textContent=(data.kind==='delivery'?'交付版本':'候选版本')+' · '+p.page+'/'+data.pages.length+' · 视觉状态：'+({'not_reviewed':'未查看','reviewed':'已查看','needs_fix':'待修正'}[p.visual.status]||p.visual.status);el('issues').textContent='程序检查：'+JSON.stringify(p.checks)+'\\n'+(p.issues.map(x=>'['+(x.element||'页面')+'] '+x.message).join('\\n')||'没有已记录的阻断问题')+'\\n源稿提示（须逐项核对；警告不阻断导出）：'+((p.sourceIssues||[]).map(x=>'['+x.severity+' · '+x.code+' · '+(x.element||x.field||'页面')+'] '+x.message).join('\\n')||'没有已记录的源稿提示')+'\\n审阅记录：'+(p.visual.note||'尚未记录；图片存在不代表审阅通过');}
function list(){el('list').replaceChildren();for(const [i,p] of data.pages.entries()){if(el('filter').value==='changed'&&!p.changed)continue;if(el('filter').value==='issues'&&!hasIssues(p))continue;const b=document.createElement('button');if(p.image){const im=document.createElement('img');im.src=p.image;im.alt='';b.append(im);}b.append(document.createTextNode(p.page+' · '+p.title));b.onclick=()=>show(i);el('list').append(b);}}
function matches(p){return el('filter').value==='all'||(el('filter').value==='changed'?p.changed:hasIssues(p));}function move(d){const ids=data.pages.flatMap((p,i)=>matches(p)?[i]:[]);if(ids.length)show(ids[(Math.max(0,ids.indexOf(selected))+d+ids.length)%ids.length]);}el('prev').onclick=()=>move(-1);el('next').onclick=()=>move(1);el('filter').onchange=()=>{list();const i=data.pages.findIndex(matches);if(i>=0)show(i);else{el('title').textContent='没有匹配的页面';el('page').hidden=true;el('source').textContent='';el('issues').textContent='';}};document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')move(1);if(e.key==='ArrowLeft')move(-1);});list();show(0);</script></html>""".replace(
        "__DATA__", embedded
    )
    atomic_write(folder / "index.html", document.encode(), force=True)


def annotate(folder, number, status, note):
    folder = Path(folder).resolve()
    if status not in ("reviewed", "needs_fix"):
        raise ValueError("Visual status must be reviewed or needs_fix")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("A visual review requires a note")
    with api.lock(folder / ".review.lock"):
        data = json.loads((folder / "review.json").read_text())
        if data.get("format") != "slide-review-v1":
            raise ValueError("Unsupported review manifest")
        if (
            not data.get("pptx")
            or not Path(data["pptx"]).is_file()
            or api.sha(Path(data["pptx"]).read_bytes()) != data["pptxHash"]
        ):
            raise ValueError(
                "Reviewed PPTX changed or is unavailable; generate a new review"
            )
        if not api.unchanged(data["tracked"]):
            raise ValueError("Source changed; generate a new review")
        if not 1 <= number <= len(data["pages"]):
            raise ValueError("Page out of range")
        data["pages"][number - 1]["visual"] = {"status": status, "note": note.strip()}
        save(folder, data)
    return {
        "status": "recorded",
        "page": number,
        "visual": data["pages"][number - 1]["visual"],
        "review": {
            "manifest": str(folder / "review.json"),
            "viewer": str(folder / "index.html"),
        },
    }
