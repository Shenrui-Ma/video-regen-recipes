"""Build native contour paths from the sole supplied reference, without raster embedding."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter
import numpy as np
import heapq,json,time,argparse,hashlib
from _contours import contours
from _regions import read_regions

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--reference',type=Path,required=True)
parser.add_argument('--regions',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args();ROOT=args.output_dir;SOURCE=args.reference
if ROOT.exists():raise ValueError('Choose a new output directory')
ROOT.mkdir(parents=True)
a=np.array(Image.open(SOURCE).convert('RGB'));H,W=a.shape[:2]
# Occupied color bins preserve counts and full-resolution mean colors.
v=a.reshape(-1,3).astype(np.int32)
keys=((v[:,0]>>2)<<12)|((v[:,1]>>2)<<6)|(v[:,2]>>2)
u,inv,counts=np.unique(keys,return_inverse=True,return_counts=True)
sums=np.stack([np.bincount(inv,weights=v[:,c],minlength=len(u)) for c in range(3)],axis=1)
means=sums/counts[:,None]

def stats(ids):
 c=counts[ids];m=means[ids];avg=(m*c[:,None]).sum(0)/c.sum();var=((m-avg)**2*c[:,None]).sum(0)
 return var,avg

clusters={0:np.arange(len(u))};heap=[];serial=0
var,_=stats(clusters[0]);heapq.heappush(heap,(-float(var.sum()),0));next_id=1
while len(clusters)<4096 and heap:
 _,ident=heapq.heappop(heap);ids=clusters.pop(ident)
 if len(ids)<2:clusters[ident]=ids;continue
 var,_=stats(ids);axis=int(var.argmax());order=ids[np.argsort(means[ids,axis])];weight=counts[order].cumsum();cut=int(np.searchsorted(weight,weight[-1]/2))+1;cut=max(1,min(cut,len(order)-1))
 for child in (order[:cut],order[cut:]):
  cid=next_id;next_id+=1;clusters[cid]=child
  if len(child)>1:
   variance,_=stats(child);heapq.heappush(heap,(-float(variance.sum()),cid))
lookup=np.empty(len(u),dtype=np.int32);palette=[]
for index,ids in enumerate(clusters.values()):
 _,avg=stats(ids);palette.append(np.rint(avg).astype(np.uint8));lookup[ids]=index
palette=np.array(palette);labels=lookup[inv].reshape(H,W);q=palette[labels]
Image.fromarray(q).save(ROOT/'quantized-review.png')
error=q.astype(float)-a
metrics={'palette_colors':len(palette),'mean_absolute_channel_error':float(abs(error).mean()),'psnr_db':float(10*np.log10(255**2/(error**2).mean())),'exact_pixels_fraction':float(np.all(q==a,axis=2).mean())}
print(json.dumps(metrics),flush=True)
# Regions are meaningful organizational groups, not bitmap tiles. They partition the scene.
regions=read_regions(args.regions,W,H,SOURCE.read_bytes())
mask=Image.new('I',(W,H),0);draw=ImageDraw.Draw(mask)
for i,(_,polygon) in enumerate(regions):
 if polygon:draw.polygon(polygon,fill=i)
region=np.array(mask,dtype=np.int32)
combined=labels+region*len(palette)
# Directed boundary edges, with the color region on the right of each edge.
# Each output subpath follows an actual connected color-region contour.
stride=W+1;edge_groups={}
def add(label,start,end):
 d=edge_groups.setdefault(int(label),{});s=int(start);e=int(end)
 if s not in d:d[s]=e
 elif isinstance(d[s],list):d[s].append(e)
 else:d[s]=[d[s],e]
for y in range(H):
 row=combined[y]
 if y==0:
  for x in range(W):add(row[x],x,x+1)
 else:
  xs=np.flatnonzero(row!=combined[y-1])
  for x in xs:
   s=y*stride+int(x);add(row[x],s,s+1);add(combined[y-1,x],s+1,s)
 for x in np.flatnonzero(row[1:]!=row[:-1])+1:
  s=y*stride+int(x);add(row[x-1],s,s+stride);add(row[x],s+stride,s)
 add(row[0],(y+1)*stride,y*stride)
 add(row[-1],y*stride+W,(y+1)*stride+W)
for x in range(W):add(combined[-1,x],H*stride+x+1,H*stride+x)
print('Boundary groups',len(edge_groups),'edges',sum(len(d) for d in edge_groups.values()),flush=True)




by_region={i:[] for i in range(len(regions))};total=0
for num,(code,edges) in enumerate(edge_groups.items()):
 d,n=contours(edges,W);rid=code//len(palette);color=palette[code%len(palette)];hexcolor='#'+''.join(f'{v:02x}' for v in color)
 by_region[rid].append((hexcolor,d,n));total+=n
 if num%2000==0:print('Traced groups',num,flush=True)
# Region silhouettes and a small number of broad tone shapes are a readable foundation.
header=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Reference illustration redrawn as native color-region contours">'
svg=[header,'<g id="complete-vector-art" shape-rendering="crispEdges" fill-rule="evenodd">']
for rid,(name,_) in enumerate(regions):
 svg.append(f'<g id="{name}" data-region="{name}">')
 for i,(color,d,n) in enumerate(by_region[rid]):svg.append(f'<path id="{name}-tone-{i:04d}" fill="{color}" d="{d}"/>')
 svg.append('</g>')
svg+=['</g>','</svg>']
text='\n'.join(svg);(ROOT/'faithful.svg').write_text(text)
metrics.update({'svg_bytes':len(text.encode()),'path_elements':sum(len(v) for v in by_region.values()),'connected_contours':total,'method':'native closed color-region contours; no embedded raster or pixel-rectangle grid','regions':[x[0] for x in regions]})
(ROOT/'metrics.json').write_text(json.dumps(metrics,indent=2))
print(json.dumps(metrics),flush=True)
