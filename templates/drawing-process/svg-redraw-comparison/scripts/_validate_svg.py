"""Validate the native contour SVG expected by the replay builder."""
import math,re,xml.etree.ElementTree as ET
NS='{http://www.w3.org/2000/svg}'
def read_contours(text,width,height,region_names):
 if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('SVG declarations are not allowed')
 root=ET.fromstring(text)
 if root.tag!=NS+'svg':raise ValueError('Expected a native SVG root')
 box=[float(n) for n in root.get('viewBox','').replace(',',' ').split()]
 if box!=[0,0,width,height]:raise ValueError('SVG dimensions differ from the reference')
 for node in root.iter():
  if node.tag not in {NS+'svg',NS+'g',NS+'path'}:raise ValueError('This builder accepts contour SVG groups and paths only')
  for key,value in node.attrib.items():
   if key.startswith('{') or key.lower().startswith('on') or key.lower() in {'href','style'} or re.search(r'data:|https?:|file:|javascript:|url\(',value,re.I):raise ValueError('External content, raster data or active attributes are forbidden')
 groups=list(root)
 if len(groups)!=1 or groups[0].get('id')!='complete-vector-art':raise ValueError('Use the SVG produced by trace_reference.py')
 regions=list(groups[0])
 if [g.get('data-region') for g in regions]!=region_names:raise ValueError('SVG region order differs from annotations')
 for g in regions:
  for p in g:
   if p.tag!=NS+'path' or not re.fullmatch('#[0-9a-fA-F]{6}',p.get('fill','')) or not p.get('d'):raise ValueError('Malformed color-region path')
 return root
