"""Offline character preparation tests; never connect to ComfyUI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/character/prepare_character.py'


def load_module():
    spec = importlib.util.spec_from_file_location('prepare_character', SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CharacterInputTests(unittest.TestCase):
    def test_local_image_preserved_without_style_change(self):
        self.assertTrue(SCRIPT.is_file(), 'standalone character entry is missing')
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'identity.jpg'
            Image.new('RGB', (16, 24), 'red').save(source)
            out = Path(tmp) / 'prepared'
            with patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
                result = m.main(['--image', str(source), '--out-dir', str(out)])
            self.assertEqual(result, 0)
            p = json.loads((out / 'provenance.json').read_text())
            self.assertEqual(p['source']['kind'], 'local')
            self.assertEqual((out / 'source.jpg').read_bytes(), source.read_bytes())
            self.assertEqual(p['style_change'], False)
            with Image.open(out / 'character.png') as image:
                self.assertEqual(image.size, (16, 24))

    def test_explicit_background_composites_alpha_at_original_dimensions(self):
        import hashlib
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'cutout.png'
            image = Image.new('RGBA', (2352, 2352), (240, 10, 20, 0))
            image.putpixel((1, 0), (0, 0, 0, 128))
            image.putpixel((2, 0), (12, 34, 56, 255))
            image.save(source)
            original = source.read_bytes()
            out = Path(tmp) / 'white'
            with patch('urllib.request.urlopen', side_effect=AssertionError('offline')):
                try:
                    status = m.main(['--image', str(source), '--background', '#FFFFFF', '--out-dir', str(out)])
                except SystemExit as error:
                    self.fail(f'Explicit alpha compositing CLI is missing: {error}')
                self.assertEqual(status, 0)
            with Image.open(out / 'character.png') as result:
                self.assertEqual(result.mode, 'RGB')
                self.assertEqual(result.size, (2352, 2352))
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(result.getpixel((1, 0)), (127, 127, 127))
                self.assertEqual(result.getpixel((2, 0)), (12, 34, 56))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual((out / 'source.png').read_bytes(), original)
            provenance = json.loads((out / 'provenance.json').read_text())
            self.assertEqual(provenance['source']['sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(provenance['character']['sha256'], hashlib.sha256((out / 'character.png').read_bytes()).hexdigest())
            self.assertEqual(provenance['preprocessing']['background'], '#FFFFFF')
            self.assertEqual(provenance['preprocessing']['alpha_composited'], True)
            self.assertEqual(provenance['preprocessing']['output_mode'], 'RGB')
            self.assertEqual(provenance['preprocessing']['output_size'], [2352, 2352])

    def test_palette_transparency_composited_on_white_by_default(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'palette.png'
            image = Image.new('P', (2, 1))
            image.putpalette([240, 10, 20, 0, 0, 0] + [0] * 762)
            image.putdata([0, 1])
            image.save(source, transparency=bytes([0, 128]))
            white = Path(tmp) / 'white'
            m.main(['--image', str(source), '--out-dir', str(white)])
            with Image.open(white / 'character.png') as result:
                self.assertEqual(result.mode, 'RGB')
                self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(result.getpixel((1, 0)), (127, 127, 127))
            out = Path(tmp) / 'solid'
            m.main(['--image', str(source), '--background', '#204060', '--out-dir', str(out)])
            with Image.open(out / 'character.png') as result:
                self.assertEqual(result.mode, 'RGB')
                self.assertEqual(result.getpixel((0, 0)), (32, 64, 96))
                self.assertEqual(result.getpixel((1, 0)), (16, 32, 48))
            self.assertTrue(json.loads((out / 'provenance.json').read_text())['preprocessing']['alpha_composited'])

    def test_default_is_h3_safe_for_rgba_la_and_rgb_transparency(self):
        m = load_module()
        cases = [('RGBA', (240, 10, 20, 0), {}), ('LA', (90, 0), {}),
                 ('RGB', (240, 10, 20), {'transparency': (240, 10, 20)}),
                 ('L', 90, {'transparency': 90})]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (mode, color, options) in enumerate(cases):
                with self.subTest(mode=mode):
                    source = Path(tmp) / f'{index}.png'
                    Image.new(mode, (3, 5), color).save(source, **options)
                    out = Path(tmp) / f'out-{index}'
                    m.main(['--image', str(source), '--out-dir', str(out)])
                    with Image.open(out / 'character.png') as result:
                        self.assertEqual(result.mode, 'RGB')
                        self.assertEqual(result.size, (3, 5))
                        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
                    p = json.loads((out / 'provenance.json').read_text())
                    self.assertEqual(p['preprocessing']['background'], '#FFFFFF')
                    self.assertTrue(p['preprocessing']['alpha_composited'])

    def test_invalid_background_refused_before_io(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            for index, color in enumerate(('white', '#FFF', '#FFFFFFFF', '#GG0000', '', ' #FFFFFF')):
                out = Path(tmp) / str(index)
                with self.subTest(color=color), patch.object(m, 'open_public', side_effect=AssertionError('must not download')):
                    with self.assertRaisesRegex(ValueError, '#RRGGBB'):
                        m.main(['--url', 'https://example.org/image.png', '--background', color, '--out-dir', str(out)])
                    self.assertFalse(out.exists())

    def test_png_conversion_never_overwrites_existing_files(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'original.png'
            Image.new('RGBA', (4, 6), (10, 20, 30, 0)).save(source)
            original = source.read_bytes()
            existing = Path(tmp) / 'existing.png'
            existing.write_bytes(b'keep this file')
            for target in (source, existing):
                before = target.read_bytes()
                with self.subTest(target=target), self.assertRaises(FileExistsError):
                    m.image_to_png(source, target, '#FFFFFF')
                self.assertEqual(target.read_bytes(), before)
            self.assertEqual(source.read_bytes(), original)

    def test_opaque_rgb_and_exif_orientation_are_preserved(self):
        from PIL import ImageOps
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'opaque.jpg'
            image = Image.new('RGB', (3, 5), (12, 34, 56))
            image.putpixel((0, 0), (220, 30, 50))
            exif = Image.Exif()
            exif[274] = 6
            image.save(source, exif=exif)
            with Image.open(source) as decoded:
                expected = ImageOps.exif_transpose(decoded).convert('RGB')
            for index, extra in enumerate(([], ['--background', '#aBcD12'])):
                out = Path(tmp) / str(index)
                m.main(['--image', str(source), '--out-dir', str(out)] + extra)
                with Image.open(out / 'character.png') as result:
                    self.assertEqual(result.mode, 'RGB')
                    self.assertEqual(result.size, expected.size)
                    self.assertEqual(result.tobytes(), expected.tobytes())
                    self.assertNotIn(274, result.getexif())
                self.assertFalse(json.loads((out / 'provenance.json').read_text())['preprocessing']['alpha_composited'])
            # CLI refuses an existing output directory, with no partial updates.
            out = Path(tmp) / '1'
            before = (out / 'character.png').read_bytes()
            with self.assertRaises(FileExistsError):
                m.main(['--image', str(source), '--out-dir', str(out)])
            self.assertEqual((out / 'character.png').read_bytes(), before)

    def test_url_download_hash_decode_and_no_partial_publish(self):
        import io
        import hashlib
        m = load_module()
        self.assertTrue(hasattr(m, 'open_public'), 'public URL downloader missing')
        buf = io.BytesIO()
        Image.new('RGB', (10, 12), 'blue').save(buf, format='PNG')
        data = buf.getvalue()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'url'
            with patch.object(m, 'open_public', return_value=io.BytesIO(data)):
                m.main(['--url', 'https://example.org/character.png', '--sha256', hashlib.sha256(data).hexdigest(), '--out-dir', str(out)])
            p = json.loads((out / 'provenance.json').read_text())
            self.assertEqual(p['source']['kind'], 'url')
            self.assertEqual(p['source']['sha256'], hashlib.sha256(data).hexdigest())
            self.assertFalse(list(out.glob('*.part')))
            bad = Path(tmp) / 'bad'
            with patch.object(m, 'open_public', return_value=io.BytesIO(data)):
                with self.assertRaises(ValueError):
                    m.main(['--url', 'https://example.org/character.png', '--sha256', '0' * 64, '--out-dir', str(bad)])
            self.assertFalse((bad / 'character.png').exists())

    def test_url_refuses_private_addresses_and_output_symlinks(self):
        m = load_module()
        self.assertTrue(hasattr(m, 'validate_public_url'), 'public URL validation missing')
        for url in ('file:///etc/passwd', 'http://127.0.0.1/x', 'https://user:pass@example.org/x', 'http://[::1]/x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.validate_public_url(url)
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / 'real'
            real.mkdir()
            alias = Path(tmp) / 'alias'
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                m.main(['--image', str(real/'source.png'), '--out-dir', str(alias / 'new')])

    def test_invalid_url_image_never_published_and_partial_removed(self):
        import io
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'bad-image'
            with patch.object(m, 'open_public', return_value=io.BytesIO(b'not an image')):
                with self.assertRaises(OSError):
                    m.main(['--url', 'https://example.org/image.png', '--out-dir', str(out)])
            self.assertFalse((out / 'character.png').exists())
            self.assertFalse((out / 'download.part').exists(), 'failed decode leaves .part')

    def test_input_entry_has_no_image_generation_capability(self):
        m = load_module()
        self.assertFalse(hasattr(m, 'ComfyHTTP'), 'Reference acquisition must not submit image generation')
        help_result = subprocess.run([sys.executable, str(SCRIPT), '--help'], text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0)
        for flag in ('--text', '--execute', '--host', '--allow-unverified-identity'):
            self.assertNotIn(flag, help_result.stdout)
        self.assertIn('--image', help_result.stdout)
        self.assertIn('--url', help_result.stdout)


if __name__ == '__main__':
    unittest.main()
