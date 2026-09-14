import importlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))

class MediaTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg needed')
    def test_dynamic_reference_and_published_only_music(self):
        self.assertTrue((RUNTIME / 'media.py').exists(), 'runtime media pipeline missing')
        m = importlib.import_module('media')
        import graphs
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = p / 'driver.mp4'; music = p / 'music.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x32:rate=24', '-frames:v', '47', '-c:v', 'libx264', str(source)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', str(music)], check=True)
            rows = graphs.plan_segments(47, 39, 22)
            records = m.prepare_references(source, p / 'refs', rows)
            self.assertEqual([x['frames'] for x in records], [39, 39])
            self.assertEqual(records[1]['driver_start'], 17)
            self.assertEqual(records[1]['padded_frames'], 9)
            published = []
            for row, record in zip(rows, records):
                out = p / ('pub%d.mp4' % row['segment'])
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(p / 'refs' / record['file']), '-vf', 'trim=start_frame=%d:end_frame=%d,setpts=PTS-STARTPTS' % (row['head_trim_frames'], row['publish_end']), '-an', '-c:v', 'libx264', str(out)], check=True)
                published.append(out)
            result = m.assemble(published, music, p / 'final', rows, width=64, height=32)
            self.assertEqual(result['frames'], 47)
            self.assertEqual(result['audio_tracks'], 1)
            self.assertTrue(result['full_decode'])
            self.assertTrue(result['decoded_frames_match_inputs'])
            self.assertEqual(result['decoded_frame_count'], 47)
            self.assertEqual(m.assemble(published, music, p / 'final', rows, width=64, height=32), result)
            with self.assertRaises(ValueError): m.assemble(published[:1], music, p / 'wrong', rows, width=64, height=32)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg needed')
    def test_failed_mux_never_publishes_partial_and_resumes_cpu_only(self):
        m = importlib.import_module('media')
        import graphs
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = p / 'published.mp4'; music = p / 'music.wav'; assembly = p / 'assembly'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x32:rate=24',
                            '-frames:v', '22', '-c:v', 'libx264', str(source)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=1', str(music)], check=True)
            rows = graphs.plan_segments(22, 22, 22)
            real_run = subprocess.run
            def fail_aac(cmd, **kwargs):
                if '-c:a' in cmd:
                    Path(cmd[-1]).write_bytes(b'partial AAC mux')
                    raise subprocess.CalledProcessError(1, cmd, stderr='experimental AAC')
                return real_run(cmd, **kwargs)
            with patch.object(m.subprocess, 'run', side_effect=fail_aac):
                with self.assertRaises(subprocess.CalledProcessError):
                    m.assemble([source], music, assembly, rows, width=64, height=32)
            self.assertFalse((assembly / 'final.mp4').exists(), 'failed mux poisoned final.mp4')
            self.assertFalse((assembly / 'verification.json').exists())
            source_sha = m.digest(source)
            silent_stamp = (assembly / 'silent.mp4').stat().st_mtime_ns
            real_hashes = m.decoded_frame_hashes
            def wrong_final_pixels(path):
                return ['changed'] if Path(path).name.startswith('final.mp4') else real_hashes(path)
            with patch.object(m, 'decoded_frame_hashes', side_effect=wrong_final_pixels):
                with self.assertRaisesRegex(ValueError, 'CONCAT_DECODED_FRAMES_CHANGED'):
                    m.assemble([source], music, assembly, rows, width=64, height=32)
            self.assertFalse((assembly / 'final.mp4').exists(), 'pixel verification must precede publication')
            result = m.assemble([source], music, assembly, rows, width=64, height=32)
            self.assertTrue(result['full_decode'])
            self.assertTrue(result['decoded_frames_match_inputs'])
            self.assertEqual(m.digest(source), source_sha)
            self.assertEqual((assembly / 'silent.mp4').stat().st_mtime_ns, silent_stamp)
            self.assertFalse(list(assembly.glob('*.part')))
            self.assertFalse(list(assembly.glob('*.pending.json')))
            receipt_path = assembly / 'verification.json'
            final = assembly / 'final.mp4'
            receipt_bytes, final_bytes = receipt_path.read_bytes(), final.read_bytes()
            final.write_bytes(final_bytes + b'changed-but-still-decodable')
            with self.assertRaisesRegex(ValueError, 'COMPLETED_ASSEMBLY_CHANGED'):
                m.assemble([source], music, assembly, rows, width=64, height=32)
            self.assertEqual(receipt_path.read_bytes(), receipt_bytes)
            self.assertEqual(final.read_bytes(), final_bytes + b'changed-but-still-decodable')

    def test_existing_invalid_media_is_preserved_with_explicit_recovery_error(self):
        m = importlib.import_module('media')
        with tempfile.TemporaryDirectory() as tmp:
            final = Path(tmp) / 'final.mp4'
            final.write_bytes(b'legacy failed mux')
            def invalid(path):
                raise ValueError('PUBLISHED_VIDEO_CONTRACT')
            with patch.object(m.subprocess, 'run', side_effect=AssertionError('must not overwrite')):
                with self.assertRaisesRegex(ValueError, 'EXISTING_ASSEMBLY_MEDIA_INVALID.*new assembly directory'):
                    m._publish_media(final, [], invalid)
            self.assertEqual(final.read_bytes(), b'legacy failed mux')

    def test_unknown_artifacts_even_with_matching_intent_are_untouched(self):
        m = importlib.import_module('media')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = p / 'source.mp4'; music = p / 'music.wav'
            source.write_bytes(b'source'); music.write_bytes(b'music')
            rows = [{'segment': 1, 'timeline_start': 0, 'timeline_end': 22, 'visible_frames': 22}]
            identity = {'inputs': [{'sha256': m.digest(source), 'visible_frames': 22}],
                        'music_sha256': m.digest(music), 'rows': rows, 'width': 64, 'height': 32}
            for name in ('unrelated.txt', 'final.mp4.part', 'concat.txt'):
                with self.subTest(name=name):
                    assembly = p / name.replace('.', '-')
                    assembly.mkdir()
                    (assembly / 'assembly-intent.json').write_text(json.dumps(identity))
                    artifact = assembly / name
                    if name == 'concat.txt':
                        artifact.symlink_to(source)
                    else:
                        artifact.write_bytes(b'unknown')
                    with patch.object(m, 'verify_video', side_effect=AssertionError('fail before media I/O')):
                        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EXISTING_ASSEMBLY'):
                            m.assemble([source], music, assembly, rows, width=64, height=32)
                    self.assertTrue(artifact.is_symlink() if name == 'concat.txt' else artifact.read_bytes() == b'unknown')
                    self.assertEqual(source.read_bytes(), b'source')

    def test_checkpoint_temporal_contract(self):
        m = importlib.import_module('media')
        self.assertTrue(hasattr(m, 'validate_segment_latent'), 'segment-aware latent validation missing')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'audio.latent'
            for length, valid in [(37, True), (36, False)]:
                size = 1 * 32 * 2 * length * 4
                h = {'latent_tensor': {'dtype': 'F32', 'shape': [1, 32, 2, length], 'data_offsets': [0, size]}, 'latent_format_version_0': {'dtype': 'F32', 'shape': [0], 'data_offsets': [size, size]}}
                b = json.dumps(h).encode(); p.write_bytes(struct.pack('<Q', len(b)) + b + bytes(size))
                if valid:
                    self.assertEqual(m.validate_segment_latent(p, 'audio', 22)['shape'][-1], 37)
                else:
                    with self.assertRaisesRegex(ValueError, 'LATENT_SEGMENT_SHAPE'):
                        m.validate_segment_latent(p, 'audio', 22)
            size = 24 * 2 * 48 * 84 * 4
            h['latent_tensor'] = {'dtype': 'F32', 'shape': [1, 24, 2, 48, 84], 'data_offsets': [0, size]}
            h['latent_format_version_0']['data_offsets'] = [size, size]
            b = json.dumps(h).encode(); p.write_bytes(struct.pack('<Q', len(b)) + b + bytes(size))
            self.assertEqual(m.validate_segment_latent(p, 'video', 5)['shape'][2], 2)
            with self.assertRaisesRegex(ValueError, 'LATENT_SEGMENT_SHAPE'):
                m.validate_segment_latent(p, 'video', 22)

    def test_checkpoint_header(self):
        self.assertTrue((RUNTIME / 'media.py').exists(), 'checkpoint validator missing')
        m = importlib.import_module('media')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'v.latent'
            h = {'latent_tensor': {'dtype': 'F32', 'shape': [1, 24, 2, 2, 2], 'data_offsets': [0, 768]}, 'latent_format_version_0': {'dtype': 'F32', 'shape': [0], 'data_offsets': [768, 768]}}
            b = json.dumps(h).encode(); p.write_bytes(struct.pack('<Q', len(b)) + b + bytes(768))
            self.assertEqual(m.validate_latent(p, 'video')['dtype'], 'F32')
            with self.assertRaises(ValueError): m.validate_latent(p, 'audio')
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(ValueError): m.validate_latent(p, 'video')

if __name__ == '__main__': unittest.main()
