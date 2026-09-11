"""Separate replay geometry from HTML without simplifying or retracing any path."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
WEB=Path(__file__).resolve().parents[1]/'web'


def package_page(page,svg_path,output):
    output=Path(output);svg_path=Path(svg_path)
    match=re.search(r'<svg\b[\s\S]*?</svg>',page)
    if not match:raise ValueError('Expected the original inline replay SVG')
    art=ET.fromstring(match.group())
    final=art.find(f'{{{NS}}}g[@id="final-contours"]')
    if final is None:raise ValueError('Missing semantic painting groups')
    source=ET.fromstring(svg_path.read_text())
    source_paths={p.attrib['id']:p.attrib for p in source.iter(f'{{{NS}}}path')}
    replay_paths={p.attrib['id']:p.attrib for p in final.iter(f'{{{NS}}}path')}
    if source_paths!=replay_paths:raise ValueError('Static SVG and replay paths differ')
    stages={p.attrib['id']:g.attrib['data-stage'][0] for g in final for p in g}
    regions=source.find(f'{{{NS}}}g[@id="complete-vector-art"]')
    if regions is None:raise ValueError('Missing source regions')
    stage_index={g.attrib['data-region']:''.join(stages[p.attrib['id']] for p in g) for g in regions}
    art.remove(final)
    foundations=ET.tostring(art,encoding='utf-8')
    payloads={'redraw.svg':svg_path.read_bytes(),'foundations.svg':foundations}
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()}
    manifest['stages']=stage_index
    controls='<p id="load-status" role="status">正在加载本地 SVG…</p><input id="svg-files" type="file" accept=".svg" multiple hidden aria-label="选择 redraw.svg 和 foundations.svg">'
    page=page[:match.start()]+page[match.end():]
    page=page.replace('<div class="frame">',controls+'<div class="frame">',1)
    page=page.replace('单文件离线播放','轻量 HTML · 本地 SVG 数据')
    loader=(WEB/'load-art.js').read_text()
    player=(WEB/'player.js').read_text()
    script='<script type="application/json" id="art-manifest">'+json.dumps(manifest)+'</script><script>'+loader+'\nloadArt().then(()=>{\n'+player+'\n}).catch(error=>{document.getElementById("load-status").textContent=error.message;document.body.dataset.error="true";});</script>'
    page=re.sub(r'<script>[\s\S]*?</script>',lambda _:script,page,count=1)
    if len(page.encode())>=200000:raise ValueError('HTML exceeds 200 kB')
    output.parent.mkdir(parents=True,exist_ok=True)
    for name,data in payloads.items():
        dest=output.parent/name
        if dest.exists():
            if dest.read_bytes()!=data:raise ValueError('Existing vector asset differs: '+name)
        else:
            with dest.open('xb') as f:f.write(data)
    with output.open('x',encoding='utf-8') as f:f.write(page)
    return {'html_bytes':len(page.encode()),'vector_files':{name:{'bytes':len(data),'sha256':manifest[name]} for name,data in payloads.items()},'path_count':len(source_paths),'simplified':False,'requires_local_svg_files':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html',type=Path,required=True);parser.add_argument('--svg',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(package_page(args.html.read_text(),args.svg,args.output),indent=2))
