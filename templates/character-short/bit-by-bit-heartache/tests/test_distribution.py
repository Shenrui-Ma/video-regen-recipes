import importlib.util
import tempfile
from pathlib import Path
import hashlib
import json
import unittest
import zipfile
import subprocess
import sys
from unittest.mock import patch

T=Path(__file__).resolve().parents[1]

def load(name):
    path=T/'scripts/distribution'/f'{name}.py'
    if not path.exists(): return None
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

class AssetTests(unittest.TestCase):
    def test_public_manifest_covers_historical_media_as_opt_in(self):
        m=load('fetch_assets'); self.assertIsNotNone(m)
        rows=json.loads((T/'assets/runtime-assets.json').read_text())['assets']
        paths={r['path']:r for r in rows}
        self.assertEqual(len(rows),len(paths))
        historical=json.loads((T/'assets/default/manifest.json').read_text())['assets']
        for old in historical:
            name='default/'+old['path']
            self.assertIn(name,paths)
            self.assertEqual(paths[name]['sha256'],old['sha256'])
            self.assertEqual(paths[name]['bytes'],old['bytes'])
        for row in rows:
            m.validate(T/'assets',row)
            self.assertIs(type(row.get('download_by_default')),bool)
        self.assertEqual({r['path'] for r in rows if r['download_by_default']},
                         {'reference/heartache-driver-577f.mp4','default/music.m4a'})
        driver=paths['reference/heartache-driver-577f.mp4']
        self.assertEqual(driver['bytes'],160208343)
        self.assertEqual(driver['sha256'],'e63386ab88bf4a11dc2fd859b0075099229cad44d77366a220c6e0bb0ba0ca0d')
        self.assertEqual(driver['video']['frames'],577)
        self.assertNotEqual(driver['sha256'],paths['default/driver.mp4']['sha256'])

    def test_default_cli_check_does_not_require_optional_photo_or_history(self):
        rows=json.loads((T/'assets/runtime-assets.json').read_text())['assets']
        expected={'reference/heartache-driver-577f.mp4','default/music.m4a'}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); manifest=p/'manifest.json'; fixture_rows=[]
            for row in rows:
                data=('offline fixture '+row['path']).encode()
                fixture_rows.append({**row,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                if row['path'] in expected:
                    f=p/'assets'/row['path']; f.parent.mkdir(parents=True,exist_ok=True); f.write_bytes(data)
            manifest.write_text(json.dumps({'assets':fixture_rows}))
            result=subprocess.run([sys.executable,str(T/'scripts/distribution/fetch_assets.py'),
                                   '--asset-root',str(p/'assets'),'--manifest',str(manifest),'--check'],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual({r['path'] for r in report['assets']},expected)
            self.assertFalse((p/'assets/default/yaoguang.png').exists())

    def test_cli_selects_only_explicit_optional_assets_and_rejects_unknown(self):
        row=next(r for r in json.loads((T/'assets/runtime-assets.json').read_text())['assets']
                 if r['path']=='default/yaoguang.png')
        data=b'offline optional image fixture'
        row={**row,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); cache=p/'cache'; cache.mkdir(); (cache/'yaoguang.png').write_bytes(data)
            manifest=p/'manifest.json'; manifest.write_text(json.dumps({'assets':[row]}))
            command=[sys.executable,str(T/'scripts/distribution/fetch_assets.py'),
                     '--asset-root',str(p/'assets'),'--manifest',str(manifest),'--cache-dir',str(cache)]
            bad=subprocess.run(command+['--assets','unknown.png'],capture_output=True,text=True)
            self.assertEqual(bad.returncode,2)
            self.assertIn('Unknown asset path',bad.stderr)
            self.assertFalse((p/'assets').exists())
            result=subprocess.run(command+['--assets','default/yaoguang.png'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)['assets'],[
                {'path':'default/yaoguang.png','status':'copied_verified_cache','sha256':row['sha256']}])
            self.assertEqual((p/'assets/default/yaoguang.png').read_bytes(),data)
            checked=subprocess.run(command+['--check','--assets','default/yaoguang.png'],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)

    def test_verified_cache_copy_idempotent_and_rejects_bad_source(self):
        m=load('fetch_assets'); self.assertIsNotNone(m,'asset acquisition helper missing')
        data=b'offline-test-only'
        row={'path':'reference/driver.mp4','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'url':'https://example.invalid/driver.mp4','role':'motion_reference'}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); cache=p/'cache'; cache.mkdir(); (cache/'driver.mp4').write_bytes(data)
            out=p/'assets'
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                result=m.acquire(out,row,cache)
                self.assertEqual(result['status'],'copied_verified_cache')
                self.assertEqual(m.acquire(out,row,cache)['status'],'already_verified')
            (out/'reference/driver.mp4').write_bytes(b'bad')
            with self.assertRaises(ValueError): m.acquire(out,row,cache)

    def test_rejects_traversal_and_http_before_any_write(self):
        m=load('fetch_assets'); self.assertIsNotNone(m,'asset acquisition helper missing')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'new'
            for path,url in [('../escape','https://example.invalid/a'),('/absolute','https://example.invalid/a'),('x','http://example.invalid/a')]:
                with self.assertRaises(ValueError): m.acquire(p,{'path':path,'url':url,'sha256':'a'*64,'bytes':1})
            self.assertFalse(p.exists())

    def manual_row(self):
        body=b'offline manual fallback fixture'
        return {'path':'default/music.m4a','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
                'url':'https://example.invalid/music.m4a','role':'soundtrack','download_by_default':True}

    def test_manual_mode_lists_url_target_and_hash_without_touching_network(self):
        row=self.manual_row()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); manifest=p/'manifest.json'; manifest.write_text(json.dumps({'assets':[row]}))
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                result=subprocess.run([sys.executable,str(T/'scripts/distribution/fetch_assets.py'),
                                       '--asset-root',str(p/'assets'),'--manifest',str(manifest),'--manual'],
                                      capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            entry=json.loads(result.stdout)['manual'][0]
            self.assertEqual(entry['url'],row['url'])
            self.assertEqual(entry['sha256'],row['sha256'])
            self.assertEqual(entry['bytes'],row['bytes'])
            self.assertTrue(entry['target'].endswith('assets/default/music.m4a'))
            self.assertTrue(any('浏览器' in step for step in entry['steps']))
            self.assertFalse((p/'assets').exists())

    def test_failed_fetch_returns_manual_instructions(self):
        body=b'offline manual fallback fixture'
        row={'path':'default/music.m4a','bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
             'url':'https://127.0.0.1:9/music.m4a','role':'soundtrack','download_by_default':True}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); manifest=p/'manifest.json'; manifest.write_text(json.dumps({'assets':[row]}))
            result=subprocess.run([sys.executable,str(T/'scripts/distribution/fetch_assets.py'),
                                   '--asset-root',str(p/'assets'),'--manifest',str(manifest)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr)
            report=json.loads(result.stdout)
            self.assertFalse(report['ok'])
            entry=report['manual'][0]
            self.assertEqual(entry['path'],'default/music.m4a')
            self.assertIn('sha256',entry)
            self.assertTrue(entry['error'])
            self.assertFalse((p/'assets/default/music.m4a').exists())

class PackageTests(unittest.TestCase):
    def test_default_package_is_text_only_and_full_retains_local_assets(self):
        m=load('package_skill')
        texts={'SKILL.md':'# Skill', 'LICENSE':'MIT', '.gitignore':'work/',
               'vendor/model-licenses/MiniMax-H3-LICENSE':'Model license terms',
               'vendor/model-licenses/Qwen3-VL-LICENSE':'Apache license terms',
               'vendor/fix.patch':'patch text', 'workflows/runtime.json':'{}',
               'assets/runtime-assets.json':'{"assets":[]}'}
        binaries=['assets/default/yaoguang.png','assets/default/music.m4a',
                  'assets/reference/driver.mp4','references/example.JPG',
                  'weights/model.safetensors','models/model.gguf','models/model.pt',
                  'models/model.bin','assets/video.webm','assets/audio.wav',
                  'assets/animation.gif','assets/unknown.dat','assets/extensionless',
                  'assets/binary.txt']
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); root=p/'skill'; root.mkdir()
            for name,text in texts.items():
                file=root/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_text(text)
            for name in binaries:
                file=root/name; file.parent.mkdir(parents=True,exist_ok=True); file.write_bytes(b'\x00binary fixture')
            result=m.package(root,p/'portable.zip')
            self.assertEqual(result['included_files'],len(texts))
            self.assertEqual(result['omitted_files'],len(binaries))
            with zipfile.ZipFile(p/'portable.zip') as z:
                manifest=json.loads(z.read('BUNDLE-MANIFEST.json'))
                self.assertEqual({r['path'] for r in manifest['files']},set(texts))
                self.assertEqual({r['path'] for r in manifest['omitted_downloadable_assets']},set(binaries))
                for row in manifest['omitted_downloadable_assets']:
                    self.assertEqual(row['sha256'],hashlib.sha256((root/row['path']).read_bytes()).hexdigest())
                    self.assertEqual(row['bytes'],(root/row['path']).stat().st_size)
            full=m.package(root,p/'full.zip',portable=False)
            self.assertEqual(full['included_files'],len(texts)+len(binaries))
            self.assertEqual(full['omitted_files'],0)
            for name in binaries:
                self.assertEqual((root/name).read_bytes(),b'\x00binary fixture')

    def test_zip_manifest_and_roundtrip_relocatable(self):
        m=load('package_skill'); self.assertIsNotNone(m,'packager missing')
        with tempfile.TemporaryDirectory() as td:
            p=Path(td); root=p/'skill'; root.mkdir()
            (root/'SKILL.md').write_text('---\nname: example\ndescription: Example.\n---\n# Example\n')
            (root/'assets').mkdir(); (root/'assets/reference').mkdir()
            (root/'assets/reference/driver.mp4').write_bytes(b'big media fixture')
            (root/'.test-venv').mkdir()
            (root/'.test-venv/secret-runtime').write_bytes(b'not part of skill')
            (root/'scripts').mkdir()
            (root/'scripts/handoff.json').write_text(json.dumps({'private': '/' + 'Users/developer/private-work'}))
            target=p/'bundle.zip'
            result=m.package(root,target,portable=True)
            self.assertEqual(result['included_files'],1)
            self.assertEqual(result['omitted_files'],1)
            checked=m.verify_archive(target)
            self.assertTrue(checked['verified'])
            self.assertEqual(checked['included_files'],1)
            with self.assertRaises(FileExistsError): m.package(root,target,portable=True)

if __name__=='__main__': unittest.main()
