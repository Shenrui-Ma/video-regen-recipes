import hashlib,importlib.util,json
from pathlib import Path
import struct,sys,tempfile,unittest,zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from clean_png import clean,parse,chunk,SIGNATURE
from _contours import contours
from _regions import read_regions
from _validate_svg import read_contours

class PipelineTests(unittest.TestCase):
 def test_lossless_png_cleanup(self):
  raw=b'\0'+bytes([10,20,30])*2
  original=SIGNATURE+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,2,0,0,0))+chunk(b'tEXt',b'note\0fixture')+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
  output=clean(original)
  self.assertEqual([k for k,_ in parse(output)],[b'IHDR',b'IDAT',b'IEND'])
  self.assertEqual(zlib.decompress(b''.join(v for k,v in parse(output) if k==b'IDAT')),raw)
 def test_boundary_is_closed(self):
  path,count=contours({0:1,1:3,3:2,2:0},1)
  self.assertEqual(count,1);self.assertEqual(path,'M0 0h1v1h-1v-1z')
 def test_reference_bound_regions(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'regions.json';p.write_text(json.dumps({'width':2,'height':1,'reference_sha256':hashlib.sha256(b'fixture').hexdigest(),'regions':[{'id':'background','polygon':[]}]}))
   self.assertEqual(read_regions(p,2,1,b'fixture'),[('background',[])])
   with self.assertRaises(ValueError):read_regions(p,2,1,b'other')
 def test_bad_region_geometry_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'r.json';p.write_text(json.dumps({'width':2,'height':1,'reference_sha256':hashlib.sha256(b'f').hexdigest(),'regions':[{'id':'background','polygon':[]},{'id':'subject','polygon':[[0,0],[3,0],[1,1]]}]}))
   with self.assertRaises(ValueError):read_regions(p,2,1,b'f')
 def valid(self):
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 1"><g id="complete-vector-art"><g data-region="background"><path fill="#aabbcc" d="M0 0h2v1h-2z"/></g></g></svg>'
 def test_vector_validation(self):
  read_contours(self.valid(),2,1,['background'])
  with self.assertRaises(ValueError):read_contours(self.valid(),2,1,['another'])
 def test_raster_and_active_content_rejected(self):
  for node in ['<image href="data:image/png;base64,AAAA"/>','<script/>','<foreignObject/>']:
   with self.assertRaises(ValueError):read_contours(self.valid().replace('</svg>',node+'</svg>'),2,1,['background'])
  with self.assertRaises(ValueError):read_contours(self.valid().replace('fill="#aabbcc"','onload="alert(1)" fill="#aabbcc"'),2,1,['background'])
 def test_published_demo_is_self_contained_native_svg(self):
  text=(ROOT/'examples/demo.html').read_text()
  for marker in ['<canvas','<img','<image','<foreignObject','data:image','<script src=','http://','https://']:
   if marker=='http://':
    self.assertNotIn(marker,text.replace('http://www.w3.org/2000/svg',''))
   else:self.assertNotIn(marker,text)
  self.assertIn('window.replay=',text)
if __name__=='__main__':unittest.main()
