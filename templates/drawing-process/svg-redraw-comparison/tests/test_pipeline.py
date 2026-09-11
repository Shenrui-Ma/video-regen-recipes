import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
cleaner=module('clean_png');builder=module('build_demo')

def png(w=16,h=16):
    header=struct.pack('>IIBBBBB',w,h,8,2,0,0,0)
    data=b''.join(b'\0'+b'\x10\x20\x30'*w for _ in range(h))
    return cleaner.SIGNATURE+cleaner.chunk(b'IHDR',header)+cleaner.chunk(b'tEXt',b'note\0fixture metadata')+cleaner.chunk(b'IDAT',zlib.compress(data))+cleaner.chunk(b'IEND',b'')

def svg(w=16,h=16):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'+''.join(f'<g data-phase="{name}"><path d="M1 1L8 8" fill="none" stroke="black"/></g>' for name in ['sketch','color','shadow','ink','detail'])+'</svg>'

class PipelineTests(unittest.TestCase):
    def test_png_reencoding_preserves_image_data_removes_metadata(self):
        original=png();result=cleaner.clean(original)
        self.assertEqual([k for k,_ in cleaner.parse(result)],[b'IHDR',b'IDAT',b'IEND'])
        streams=lambda data:zlib.decompress(b''.join(v for k,v in cleaner.parse(data) if k==b'IDAT'))
        self.assertEqual(streams(original),streams(result))
    def test_png_corruption_rejected(self):
        data=bytearray(png());data[20]^=1
        with self.assertRaises(ValueError):cleaner.clean(bytes(data))
    def test_raster_script_and_external_content_rejected(self):
        for bad in ['<image href="data:image/png;base64,AAAA"/>','<script>alert(1)</script>','<foreignObject/>','<path onload="alert(1)"/>','<path fill="url(https://example.com/a)"/>']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):builder.validate_svg(svg().replace('</svg>',bad+'</svg>'))
    def test_missing_stage_and_unstaged_drawing_rejected(self):
        with self.assertRaises(ValueError):builder.validate_svg(svg().replace('data-phase="ink"','data-phase="other"'))
        with self.assertRaises(ValueError):builder.validate_svg(svg().replace('</svg>','<rect width="16" height="16"/></svg>'))
    def test_example_is_vector_only_and_has_all_phases(self):
        self.assertEqual(builder.validate_svg((ROOT/'examples/redraw.svg').read_text()),[1536,1024])
    def test_layout_selection_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);reference=p/'ref.png';vector=p/'art.svg';output=p/'demo.html'
            reference.write_bytes(cleaner.clean(png(16,24)));vector.write_text(svg(16,24))
            result=builder.build(reference,vector,output,panel_width=128)
            self.assertEqual(result['layout'],'side-by-side')
            self.assertIn('window.REPLAY_CONFIG=',output.read_text())
            with self.assertRaises(ValueError):builder.build(reference,vector,output,panel_width=128)
    def test_aspect_ratio_and_timing_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);reference=p/'ref.png';vector=p/'art.svg';output=p/'demo.html'
            reference.write_bytes(png());vector.write_text(svg(16,24))
            with self.assertRaises(ValueError):builder.build(reference,vector,output)
            vector.write_text(svg())
            with self.assertRaises(ValueError):builder.build(reference,vector,output,draw=float('nan'))
            self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()
