from array import array
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import wave

from PIL import Image, ImageDraw, ImageChops

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ring_render', ROOT / 'scripts/render.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def make_audio(path, seconds=2, amplitude=18000):
    samples = array('h')
    for i in range(round(8000 * seconds)):
        value = round(amplitude * math.sin(2 * math.pi * 100 * i / 8000)) if i >= 4000 else 0
        # Opposite phase must not disappear from the energy envelope.
        samples.extend((value, -value))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())


class EnvelopeTests(unittest.TestCase):
    def test_silence_and_antiphase_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.wav'
            make_audio(path)
            env = m.rms_envelope(path, 24, 48)
            self.assertEqual(len(env), 48)
            self.assertEqual(env[:12], [0.0] * 12)
            self.assertGreater(max(env), 0.9)
            make_audio(path, amplitude=0)
            self.assertEqual(m.rms_envelope(path, 24, 48), [0.0] * 48)

    def test_tiny_noise_does_not_drive_full_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'noise.wav'
            make_audio(path, amplitude=1)
            self.assertLess(max(m.rms_envelope(path, 24, 48)), 0.01)

    def test_encoder_cleanup_closes_pipe_and_escalates_with_timeout(self):
        process = MagicMock()
        process.stdin.closed = False
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('ffmpeg', 5), 0]
        m.stop_encoder(process)
        process.stdin.close.assert_called_once()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
        for call in process.wait.call_args_list:
            self.assertEqual(call.kwargs, {'timeout': 5})


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe required')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        candidates = [os.environ.get('TEST_FONT', ''), '/System/Library/Fonts/Supplemental/Arial.ttf',
                      '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf']
        font = next((p for p in candidates if Path(p).is_file()), None)
        if not font:
            self.skipTest('Set TEST_FONT to an installed TrueType font')
        make_audio(self.root / 'master.wav')
        art = Image.new('RGB', (400, 600), '#384C47')
        draw = ImageDraw.Draw(art)
        draw.rectangle((60, 140, 340, 460), fill='#D9D8CF')
        draw.ellipse((100, 190, 300, 390), fill='#567D86')
        art.save(self.root / 'art.png')
        self.project = self.root / 'project.json'
        self.data = {'schema_version': 1, 'audio': 'master.wav',
                     'audio_sha256': m.sha256(self.root / 'master.wav'),
                     'image': 'art.png', 'font': font, 'output': 'out/clip.mp4',
                     'width': 240, 'height': 320, 'fps': 24, 'duration': 2,
                     'title': 'RING TEST', 'credit': 'Synthetic audio',
                     'cues': [{'start': 0.5, 'end': 1.5, 'lines': ['Audio-reactive rings', 'Two independent envelopes']}]}

    def load(self, data=None):
        self.project.write_text(json.dumps(self.data if data is None else data))
        return m.load_project(self.project)

    def test_validation_and_no_inference_dependency(self):
        cfg = self.load()
        self.assertEqual(cfg['frames'], 48)
        self.assertFalse(cfg['output'].exists())
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/render.py'),
                                 str(self.project), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['valid'])

    def test_reject_invalid_inputs(self):
        invalid = [dict(width=241), dict(fps=0), dict(duration=3), dict(start=1.5, duration=1),
                   dict(duration=float('nan')), dict(colors=['red', 'blue']), dict(audio_sha256='0' * 64),
                   dict(output='clip.wav'), dict(title='bad\nline'), dict(width=True),
                   dict(unknown='ignored?'), dict(audio='missing.wav'),
                   dict(cues=[{'start': 1, 'end': 0.5, 'lines': ['backwards']}]),
                   dict(cues=[{'start': 0, 'end': 1, 'lines': ['one']},
                              {'start': 0.5, 'end': 1.5, 'lines': ['overlap']}])]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises((ValueError, OSError)):
                self.load({**self.data, **change})

    def test_visual_motion_and_half_open_cue_boundaries(self):
        cfg = self.load()
        base = m.canvas(cfg)
        before = m.draw_frame(cfg, base, 0, 0, 0)
        pulse = m.draw_frame(cfg, base, 0, 1, 1)
        self.assertIsNotNone(ImageChops.difference(before, pulse).getbbox())
        self.assertIsNotNone(ImageChops.difference(before, m.draw_frame(cfg, base, 12, 0, 0)).getbbox())
        self.assertIsNone(ImageChops.difference(before, m.draw_frame(cfg, base, 36, 0, 0)).getbbox())
        font = m.fitted_font(cfg['font'], 'A very long title that should fit', 206, 48)
        self.assertLessEqual(font.getlength('A very long title that should fit'), 206)

    def test_full_render_hashes_codecs_frames_and_no_overwrite(self):
        cfg = self.load()
        hashes = [m.sha256(cfg[p]) for p in ('audio', 'image', 'font')]
        result = m.render(cfg)
        self.assertEqual(result['frames'], 48)
        self.assertTrue(result['full_decode_passed'])
        self.assertEqual(result['audio_codec'], 'aac')
        self.assertEqual(result['output_sha256'], m.sha256(cfg['output']))
        self.assertEqual(hashes, [m.sha256(cfg[p]) for p in ('audio', 'image', 'font')])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.load()
        info = m.probe(cfg['output'])
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        self.assertEqual(video['avg_frame_rate'], '24/1')
        self.assertEqual(video['pix_fmt'], 'yuv420p')
        self.assertAlmostEqual(float(info['format']['duration']), 2, delta=0.1)

    def test_replaced_source_does_not_change_snapshot_or_record(self):
        cfg = self.load()
        original_hash = cfg['audio_sha256']
        decode = m.decode_analysis

        def replace_after_analysis(snapshot, path, low_band=False):
            result = decode(snapshot, path, low_band)
            if not low_band:
                make_audio(cfg['audio'], amplitude=0)
            return result

        with patch.object(m, 'decode_analysis', side_effect=replace_after_analysis):
            result = m.render(cfg)
        self.assertEqual(result['audio_sha256'], original_hash)
        self.assertNotEqual(m.sha256(cfg['audio']), original_hash)
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(cfg['output']), '-map', '0:a:0',
                              '-f', 's16le', '-ac', '2', '-ar', '8000', 'pipe:1'],
                             capture_output=True, check=True).stdout
        samples = array('h', raw)
        if sys.byteorder != 'little':
            samples.byteswap()
        self.assertGreater(max(abs(x) for x in samples), 5000)

    def test_replaced_source_before_snapshot_is_rejected(self):
        cfg = self.load()
        make_audio(cfg['audio'], amplitude=0)
        with self.assertRaisesRegex(ValueError, 'before snapshot'):
            m.render(cfg)
        self.assertFalse(cfg['output'].exists())

    def test_short_audio_in_long_video_uses_audio_duration(self):
        container = self.root / 'long-video.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-f', 'lavfi', '-i', 'color=s=240x320:r=24:d=2',
                        '-f', 'lavfi', '-i', 'sine=frequency=100:duration=1',
                        '-c:v', 'libx264', '-c:a', 'aac', str(container)], check=True)
        data = {**self.data, 'audio': container.name, 'audio_sha256': m.sha256(container), 'cues': []}
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            self.load(data)
        data.pop('duration')
        cfg = self.load(data)
        self.assertAlmostEqual(cfg['duration'], 1, delta=.03)
        result = m.render(cfg)
        self.assertEqual(result['frames'], 24)

    def test_decoded_short_segment_cannot_be_silently_padded(self):
        cfg = self.load()
        cfg['duration'] = 3
        cfg['frames'] = 72
        with self.assertRaisesRegex(ValueError, 'Decoded audio is shorter'):
            m.decode_analysis(cfg, self.root / 'analysis.wav')

    def test_delayed_audio_stream_is_rebased_to_output_start(self):
        container = self.root / 'delayed.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-n', '-f', 'lavfi', '-i', 'color=s=240x320:r=24:d=3',
                        '-itsoffset', '0.5', '-i', str(self.root / 'master.wav'),
                        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-c:a', 'aac',
                        str(container)], check=True)
        stream = next(s for s in m.probe(container)['streams'] if s['codec_type'] == 'audio')
        self.assertGreater(float(stream['start_time']), 0.3)
        cfg = self.load({**self.data, 'audio': container.name, 'audio_sha256': m.sha256(container),
                         'duration': 1, 'cues': []})
        m.render(cfg)
        output = next(s for s in m.probe(cfg['output'])['streams'] if s['codec_type'] == 'audio')
        self.assertAlmostEqual(float(output['start_time']), 0, delta=.03)
        self.assertAlmostEqual(float(output['duration']), 1, delta=.05)

    def test_missing_stream_duration_falls_back_to_real_audio(self):
        self.assertAlmostEqual(m.audio_duration(self.root / 'master.wav', {}), 2, delta=.001)

    def test_drawing_failure_exits_without_hanging(self):
        self.load()
        code = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location('ring', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
original = m.draw_frame
calls = 0
def fail(*args):
    global calls
    calls += 1
    if calls == 4:
        raise RuntimeError('injected frame error')
    return original(*args)
m.draw_frame = fail
try:
    m.render(m.load_project(sys.argv[2]))
except RuntimeError as error:
    assert str(error) == 'injected frame error', error
else:
    raise AssertionError('expected drawing failure')
'''
        result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts/render.py'),
                                 str(self.project)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'out/clip.mp4').exists())
        self.assertFalse(list((self.root / 'out').glob('ring-*')))

    def test_landscape_segment_keeps_output_relative_cues(self):
        cfg = self.load({**self.data, 'width': 320, 'height': 240, 'start': 0.5, 'duration': 1,
                         'cues': [{'start': 0, 'end': 0.5, 'lines': ['Already trimmed']}]})
        result = m.render(cfg)
        self.assertEqual(result['source_start'], 0.5)
        self.assertEqual(result['frames'], 24)
        self.assertEqual(result['cues'][0]['start'], 0)

    def test_rings_stay_out_of_title_and_subtitle_bands(self):
        for width, height in [(240, 320), (320, 240), (1080, 1920), (1920, 1080)]:
            cfg = self.load({**self.data, 'width': width, 'height': height,
                             'title': '', 'credit': '', 'cues': []})
            base = m.canvas(cfg)
            bounds = ImageChops.difference(base, m.draw_frame(cfg, base, 0, 1, 1)).getbbox()
            self.assertGreater(bounds[1], height * 0.22)
            self.assertLess(bounds[3], height * 0.78)


if __name__ == '__main__':
    unittest.main()
