from pathlib import Path
import ast,json,html,xml.etree.ElementTree as ET,argparse
from PIL import Image,ImageDraw,ImageFilter,ImageOps
import numpy as np

parser=argparse.ArgumentParser(description='Build a native-SVG painting replay HTML, without Canvas or raster embedding.')
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--regions',type=Path,required=True)
parser.add_argument('--svg',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();ROOT=args.output.parent;SOURCE=args.reference
if args.output.exists():raise ValueError('Choose a new HTML output')
ROOT.mkdir(parents=True,exist_ok=True)
img=Image.open(SOURCE).convert('RGB');W,H=img.size;stride=W+1
from _contours import contours
from _regions import read_regions
from _validate_svg import read_contours
regions=read_regions(args.regions,W,H,SOURCE.read_bytes())
mask=Image.new('I',(W,H),0);paint=ImageDraw.Draw(mask)
for i,(_,poly) in enumerate(regions):
 if poly:paint.polygon(poly,fill=i)
region=np.array(mask);pixels=np.array(img)

def trace_binary(a):
 edges={}
 def add(s,e):
  if s not in edges:edges[s]=e
  elif isinstance(edges[s],list):edges[s].append(e)
  else:edges[s]=[edges[s],e]
 for y in range(H):
  row=a[y]
  if y==0:
   for x in np.flatnonzero(row):add(int(x),int(x)+1)
  else:
   for x in np.flatnonzero(row!=a[y-1]):
    s=y*stride+int(x)
    add(s,s+1) if row[x] else add(s+1,s)
  for x in np.flatnonzero(row[1:]!=row[:-1])+1:
   s=y*stride+int(x)
   add(s,s+stride) if row[x-1] else add(s+stride,s)
  if row[0]:add((y+1)*stride,y*stride)
  if row[-1]:add(y*stride+W,(y+1)*stride+W)
 for x in np.flatnonzero(a[-1]):add(H*stride+int(x)+1,H*stride+int(x))
 return contours(edges,W)[0]

# Edge-based ink, grouped by visible subject; no raster survives in the HTML.
gray=np.array(ImageOps.grayscale(img),dtype=np.int16)
dx=np.zeros_like(gray);dy=np.zeros_like(gray)
dx[:,1:]=abs(gray[:,1:]-gray[:,:-1]);dy[1:]=abs(gray[1:]-gray[:-1])
ink=(dx+dy)>34
outline=[];flats=[];region_luma=[]
for i,(name,poly) in enumerate(regions):
 selected=region==i;median=np.median(pixels[selected],axis=0).astype(int);region_luma.append(float(median @ np.array([.2126,.7152,.0722])))
 color='#'+''.join(f'{x:02x}' for x in median)
 flats.append(f'<path id="base-{name}" class="flat-step" data-order="{i}" fill="{color}" d="{trace_binary(selected)}"/>')
 d=trace_binary(selected&ink)
 outline.append(f'<path id="ink-{name}" class="ink-step" data-order="{i}" fill="#394459" d="{d}"/>')
 print('Prepared foundation',name,flush=True)
# The faithful color paths are partitioned into meaningfully named painting stages.
svg=read_contours(args.svg.read_text(),W,H,[name for name,_ in regions]);ns='{http://www.w3.org/2000/svg}'
buckets={key:[] for key in ['shadow','highlight','detail']}
for i,g in enumerate(svg.find(ns+'g')):
 for node in g:
  rgb=np.array([int(node.attrib['fill'][j:j+2],16) for j in (1,3,5)])
  lum=float(rgb @ np.array([.2126,.7152,.0722]))
  phase='shadow' if lum<region_luma[i]-10 else 'highlight' if lum>region_luma[i]+22 else 'detail'
  buckets[phase].append((i,node.attrib))
paint_groups=[]
for phase,entries in buckets.items():
 for rid,(name,_) in enumerate(regions):
  sub=[attrs for r,attrs in entries if r==rid]
  # Small sequential batches refine a named part; no full-picture opacity reveal.
  for offset in range(0,len(sub),64):
   attrs=sub[offset:offset+64];paths=''.join('<path '+' '.join(k+'="'+html.escape(v,quote=True)+'"' for k,v in a.items())+'/>' for a in attrs)
   paint_groups.append(f'<g id="{phase}-{name}-{offset//64}" class="paint-step" data-stage="{phase}" data-region="{name}">{paths}</g>')
sketch=[]
for i,(name,poly) in enumerate(regions):
 if poly:
  points=' '.join(f'{x},{y}' for x,y in poly)
  sketch.append(f'<polygon id="construction-{name}" points="{points}" fill="none" stroke="#8d9bb5" stroke-width="2"/>')
art=f'''<svg id="art" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" aria-label="SVG临摹重绘"><g id="construction" opacity="0">{''.join(sketch)}</g><g id="flat-colors" shape-rendering="crispEdges" fill-rule="evenodd">{''.join(flats)}</g><g id="ink" shape-rendering="crispEdges" fill-rule="evenodd">{''.join(outline)}</g><g id="final-contours" shape-rendering="crispEdges" fill-rule="evenodd">{''.join(paint_groups)}</g></svg>'''
style=(Path(__file__).resolve().parents[1]/'web'/'player.css').read_text()
script=(Path(__file__).resolve().parents[1]/'web'/'player.js').read_text()
page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>基于大模型的SVG临摹重绘</title><style>'+style+'</style></head><body><main><h1>基于大模型的SVG临摹重绘</h1><p class="sub">原生 SVG 路径 · 无 Canvas · 无图片嵌入 · 单文件离线播放</p><div class="frame">'+art+'</div><nav><button id="play">播放</button><button id="reset">重置</button><button id="final">查看完成图</button><span id="phase"></span><input id="slider" aria-label="绘制进度" type="range" min="0" max="40" step=".05" value="0"><span id="stamp"></span></nav><p class="small">连续色域轮廓矢量化，按构图、线稿、固有色、阴影、高光与细节重放。仅原生矢量，不是模型思考录屏。颜色存在量化误差，不声明逐像素零误差。</p></main><script>'+script+'</script></body></html>'
args.output.write_text(page)
args.output.with_suffix('.info.json').write_text(json.dumps({'bytes':len(page.encode()),'painting_batches':len(paint_groups),'duration_seconds':40,'external_resources':False,'canvas':False,'raster_embedding':False},indent=2))
print('Demo ready:',len(page.encode()),'bytes;',len(paint_groups),'painting batches',flush=True)
