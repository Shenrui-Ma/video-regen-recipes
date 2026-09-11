"""Read region annotations tied to an exact reference image."""
import hashlib,json,math,re

def read_regions(path,width,height,reference):
 data=json.loads(path.read_text(encoding='utf-8'))
 if data.get('reference_sha256')!=hashlib.sha256(reference).hexdigest() or (data.get('width'),data.get('height'))!=(width,height):raise ValueError('Region annotations belong to a different reference')
 result=[];seen=set()
 for i,item in enumerate(data['regions']):
  name=item['id'];points=item['polygon']
  if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9-]*',name) or name in seen:raise ValueError('Region IDs must be unique semantic names')
  if i==0 and points:raise ValueError('First region must be the uncovered background with polygon=[]')
  if i>0 and len(points)<3:raise ValueError('A subject region needs at least three vertices')
  for point in points:
   if len(point)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in point) or not (0<=point[0]<=width and 0<=point[1]<=height):raise ValueError('Invalid region vertex')
  seen.add(name);result.append((name,points))
 if not result:raise ValueError('At least a background region is required')
 return result
