#!/usr/bin/env python3
"""Build a self-contained comparison player from a clean PNG and staged vector SVG."""
import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SVG_NS='http://www.w3.org/2000/svg'
PHASES={'sketch','ink','color','shadow','detail'}
TAGS={'svg','defs','g','path','rect','circle','ellipse','line','polyline','polygon','linearGradient','radialGradient','stop','clipPath'}


def validate_svg(text):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('SVG declarations are not allowed')
    root=ET.fromstring(text)
    if root.tag!='{'+SVG_NS+'}svg':raise ValueError('Expected a namespaced SVG root')
    view=[float(v) for v in root.get('viewBox','').replace(',',' ').split()]
    if len(view)!=4 or not all(math.isfinite(v) for v in view) or view[:2]!=[0,0] or min(view[2:])<=0:raise ValueError('Use viewBox="0 0 width height"')
    phases=set();ids=set();links=[]
    for node in root.iter():
        if node.tag.removeprefix('{'+SVG_NS+'}') not in TAGS:raise ValueError('Unsupported SVG element; raster/script/foreign content is forbidden')
        for key,value in node.attrib.items():
            if key.startswith('{') or key.lower().startswith('on') or key in {'href','style'}:
                raise ValueError('SVG event handlers, href and inline CSS are not allowed')
            if re.search(r'data:|https?:|file:|javascript:',value,re.I):raise ValueError('External or raster SVG content is forbidden')
            for target in re.findall(r'url\((.*?)\)',value):
                target=target.strip(' \"\'')
                if not target.startswith('#'):raise ValueError('Only internal SVG resources are allowed')
                links.append(target[1:])
        if node.get('id'):
            if node.get('id') in ids:raise ValueError('Duplicate SVG id')
            ids.add(node.get('id'))
        if node.get('data-phase'):
            if node.get('data-phase') not in PHASES:raise ValueError('Unknown drawing phase')
            phases.add(node.get('data-phase'))
    if not set(links)<=ids:raise ValueError('SVG references a missing resource')
    if phases!=PHASES:raise ValueError('Provide sketch, ink, color, shadow and detail groups')
    for node in root:
        tag=node.tag.removeprefix('{'+SVG_NS+'}')
        if tag=='defs':continue
        if tag!='g' or node.get('data-phase') not in PHASES:raise ValueError('All visible elements must belong to phase groups')
        if not len(node) or any(child.tag.removeprefix('{'+SVG_NS+'}') in {'g','defs','svg'} for child in node):raise ValueError('Each phase must contain drawable leaf elements')
    return view[2:]


def build(reference,svg_path,output,layout='auto',panel_width=768,draw=24,lead=1,hold=3):
    if output.exists():raise ValueError('Output exists; choose a new HTML file')
    raw=reference.read_bytes()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Reference must be a PNG')
    width,height=struct.unpack_from('>II',raw,16)
    text=svg_path.read_text(encoding='utf-8');sw,sh=validate_svg(text)
    if abs(sw/sh-width/height)>.0001:raise ValueError('SVG and reference aspect ratios must agree')
    if layout=='auto':layout='stacked' if width>=height else 'side-by-side'
    if panel_width<128 or panel_width>1920 or panel_width%2:raise ValueError('Panel width must be even, 128..1920')
    if round(panel_width*height/width)%2:raise ValueError('Choose a width that gives even panel height for video')
    if not all(math.isfinite(t) for t in (draw,lead,hold)) or draw<=0 or min(lead,hold)<0 or draw+lead+hold>300:raise ValueError('Invalid timeline duration')
    cfg={'reference':'data:image/png;base64,'+base64.b64encode(raw).decode(),'width':width,'height':height,'layout':layout,'panelWidth':panel_width,'draw':draw,'lead':lead,'duration':draw+lead+hold}
    payload=json.dumps(cfg,ensure_ascii=False).replace('<','\\u003c')
    # Only validated vector markup is embedded; the reference is solely a separate image source.
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>基于大模型的SVG临摹重绘</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1120;color:#dfe8f6;font:15px system-ui,sans-serif}main{max-width:850px;margin:32px auto;padding:0 20px}h1{font-size:24px;margin-bottom:10px}p{color:#a4b4ce;line-height:1.7}canvas{display:block;width:100%;height:auto;border:1px solid #30405c;border-radius:6px}nav{display:flex;gap:12px;align-items:center;margin:18px 0}button{background:#dce8ff;color:#13233c;border:0;border-radius:6px;padding:10px 18px;cursor:pointer}input{flex:1;min-width:60px}small{display:block;color:#a4b4ce;line-height:1.6}#vector,#source{position:absolute;left:-20000px;top:0;width:1536px;height:1024px}
</style><main><h1>基于大模型的SVG临摹重绘</h1><p>对照参考图，播放从起稿、线稿到铺色、明暗与细节的 SVG 绘制步骤。</p><canvas></canvas><nav><button id="play">播放</button><button id="restart">重置</button><input id="time" type="range" min="0" step="0.01" value="0" aria-label="播放时间"><span id="status"></span></nav><small>这是 SVG 图形的分阶段绘制重放，不是模型思考过程录屏。参考图片与临摹结果分别展示。</small></main><img id="source" alt=""><div id="vector">'''+text+'''</div><script>window.REPLAY_CONFIG='''+payload+''';</script><script>'''+(ROOT/'web/player.js').read_text()+'''</script></html>'''
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(page,encoding='utf-8')
    return {'reference_sha256':hashlib.sha256(raw).hexdigest(),'svg_sha256':hashlib.sha256(text.encode()).hexdigest(),'layout':layout,'duration_seconds':cfg['duration']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--svg',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--layout',choices=['auto','stacked','side-by-side'],default='auto');p.add_argument('--panel-width',type=int,default=768)
    p.add_argument('--draw-seconds',type=float,default=24);p.add_argument('--lead-seconds',type=float,default=1);p.add_argument('--hold-seconds',type=float,default=3)
    a=p.parse_args();print(json.dumps(build(a.reference,a.svg,a.output,a.layout,a.panel_width,a.draw_seconds,a.lead_seconds,a.hold_seconds)))
if __name__=='__main__':main()
