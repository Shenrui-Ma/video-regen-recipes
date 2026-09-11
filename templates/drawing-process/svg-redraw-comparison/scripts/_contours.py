"""Trace directed color-region boundaries as closed native SVG subpaths."""
def contours(edges,width):
 stride=width+1
 def direction(a,b):
  delta=b-a
  return 0 if delta==1 else 1 if delta==stride else 2 if delta==-1 else 3
 def consume(edges,current,previous=None):
  choices=edges[current]
  if isinstance(choices,int):del edges[current];return choices
  if previous is None:index=0
  else:
   incoming=direction(previous,current);rank={1:0,0:1,3:2,2:3}
   index=min(range(len(choices)),key=lambda i:rank[(direction(current,choices[i])-incoming)%4])
  out=choices.pop(index)
  if len(choices)==1:edges[current]=choices[0]
  return out
 def trace():
  chunks=[];polygons=0
  while edges:
   start=next(iter(edges));previous=start;current=consume(edges,start);points=[start];last=direction(start,current)
   while current!=start:
    following=consume(edges,current,previous);d=direction(current,following)
    if d!=last:points.append(current)
    previous,current=current,following;last=d
   points.append(start)
   x0=start%stride;y0=start//stride;data=f'M{x0} {y0}'
   x,y=x0,y0
   for point in points[1:]:
    nx=point%stride;ny=point//stride
    if nx!=x:data+=f'h{nx-x}'
    if ny!=y:data+=f'v{ny-y}'
    x,y=nx,ny
   chunks.append(data+'z');polygons+=1
  return ''.join(chunks),polygons
 return trace()
