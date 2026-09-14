import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

T = Path(__file__).resolve().parents[1]
RUNTIME = T / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))

class CLITests(unittest.TestCase):
    def test_smoke_and_no_implicit_execution(self):
        self.assertTrue((RUNTIME / 'heartache.py').exists(), 'portable CLI missing')
        m = importlib.import_module('heartache')
        with patch.object(m, 'API', side_effect=AssertionError('network forbidden')):
            self.assertEqual(m.main(['smoke']), 0)
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / 'run.json').write_text(json.dumps({'segments': [{'segment': 1}]}))
                self.assertEqual(m.main(['run', '--work-dir', str(d)]), 0)
        result = subprocess.run([sys.executable, str(RUNTIME / 'heartache.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('prepare', result.stdout)

    def test_offline_prepare_binds_inputs_and_calibrated_plan(self):
        self.assertTrue((RUNTIME / 'heartache.py').exists(), 'portable CLI missing')
        m = importlib.import_module('heartache')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            source = p / 'driver.mp4'; music = p / 'music.wav'; character = p / 'person.png'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1344x768:rate=24', '-frames:v', '47', '-c:v', 'libx264', '-preset', 'ultrafast', str(source)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', str(music)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-frames:v', '1', str(character)], check=True)
            work = p / 'prepared'
            with patch.object(m, 'API', side_effect=AssertionError('network forbidden')):
                self.assertEqual(m.main(['prepare', '--work-dir', str(work), '--character-image', str(character), '--driver', str(source), '--music', str(music), '--frames', '47', '--max-sample-frames', '39', '--character-description', 'Person in a scarlet coat']), 0)
            config = json.loads((work / 'run.json').read_text())
            self.assertEqual(len(config['segments']), 2)
            self.assertEqual(config['segments'][-1]['visible_frames'], 8)
            graph = json.loads((work / 'segments/seg02/graph.api.json').read_text())
            self.assertIn('Person in a scarlet coat', graph['5']['inputs']['prompt'])
            self.assertEqual(graph['54']['inputs']['batch_index'], ['53', 1])
            self.assertTrue((work / 'segments/seg01/graph.editor.json').is_file())
            self.assertFalse((work / 'segments/seg01/job/state.json').exists())
            from PIL import Image
            alpha = p / 'alpha.png'
            Image.new('RGBA', (3, 5), (240, 10, 20, 0)).save(alpha)
            rejected = p / 'must-not-create'
            self.assertEqual(m.main(['prepare', '--work-dir', str(rejected), '--character-image', str(alpha), '--driver', str(source), '--music', str(music), '--frames', '47', '--max-sample-frames', '39']), 1)
            self.assertFalse(rejected.exists())

class ExecuteCLITests(unittest.TestCase):
    def test_calibration_resume_stages_both_latents_without_resampling(self):
        import struct
        m = importlib.import_module('heartache')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root / 'work'; comfy = root / 'comfy'
            (comfy / 'input').mkdir(parents=True); (comfy / 'output').mkdir()
            driver = root / 'driver.mp4'; music = root / 'music.wav'; image = root / 'person.png'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=1344x768:rate=24', '-frames:v', '47', '-c:v', 'libx264', '-preset', 'ultrafast', str(driver)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', str(music)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-i', str(driver), '-frames:v', '1', str(image)], check=True)
            self.assertEqual(m.main(['prepare', '--work-dir', str(work), '--character-image', str(image), '--driver', str(driver), '--music', str(music), '--max-sample-frames', '39']), 0)
            class FixtureAPI:
                # Explicit CPU-only fixtures, not real inference evidence.
                host = 'http://127.0.0.1:8188'; interval = 0
                posts = []; histories = {}
                def request(self, path, body=None):
                    if path == '/object_info': return m.load('node-schema.json')
                    if path == '/queue': return {'queue_running': [], 'queue_pending': []}
                    if path.startswith('/history/'):
                        pid = path.split('/')[-1]
                        return {pid: self.histories[pid]} if pid in self.histories else {}
                    if path != '/prompt': raise AssertionError(path)
                    assert body is not None
                    g = body['prompt']; self.posts.append(body)
                    for node, field in [('21', 'image'), ('22', 'file'), ('51', 'latent'), ('52', 'latent')]:
                        if node in g:
                            assert (comfy / 'input' / g[node]['inputs'][field]).is_file()
                    outputs = {}
                    for node, part in [('61', 'video'), ('62', 'audio')]:
                        filename = 'fixture-' + body['prompt_id'] + '-' + part + '.latent'
                        frames = g['5']['inputs']['length']
                        shape = [1, 24, (frames - 5) // 17 * 5 + 2, 48, 84] if part == 'video' else [1, 32, 2, round(frames / 24 * 40)]
                        size = 4
                        for dim in shape: size *= dim
                        header = json.dumps({'latent_tensor': {'dtype': 'F32', 'shape': shape, 'data_offsets': [0, size]}, 'latent_format_version_0': {'dtype': 'F32', 'shape': [0], 'data_offsets': [size, size]}}).encode()
                        (comfy / 'output' / filename).write_bytes(struct.pack('<Q', len(header)) + header + bytes(size))
                        outputs[node] = {'latents': [{'filename': filename, 'subfolder': '', 'type': 'output'}]}
                    filename = 'fixture-' + body['prompt_id'] + '.mp4'
                    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=1344x768:rate=24', '-frames:v', str(g['54']['inputs']['length']), '-c:v', 'libx264', '-preset', 'ultrafast', str(comfy / 'output' / filename)], check=True)
                    outputs['14'] = {'images': [{'filename': filename, 'subfolder': '', 'type': 'output'}]}
                    self.histories[body['prompt_id']] = {'status': {'completed': True, 'status_str': 'success'}, 'outputs': outputs}
                    return {'prompt_id': body['prompt_id']}
            api = FixtureAPI()
            command = ['run', '--work-dir', str(work), '--comfy-root', str(comfy), '--execute']
            with patch.object(m, 'API', return_value=api):
                with patch.object(m, 'preflight_media',
                                  side_effect=ValueError('FFMPEG_AAC_PREFLIGHT_FAILED')) as preflight:
                    self.assertEqual(m.main(command + ['--until-segment', '1']), 1)
                    preflight.assert_called_once_with()
                    self.assertEqual(api.posts, [], 'AAC failure must precede every new POST')
                    self.assertFalse((work / 'segments/seg01/job/state.json').exists())
                real_run = subprocess.run
                def fail_final_mux(cmd, **kwargs):
                    if '-c:a' in cmd and Path(cmd[-1]).name.startswith('final.mp4'):
                        Path(cmd[-1]).write_bytes(b'interrupted AAC mux')
                        raise subprocess.CalledProcessError(1, cmd)
                    return real_run(cmd, **kwargs)
                with patch.object(subprocess, 'run', side_effect=fail_final_mux):
                    self.assertEqual(m.main(command + ['--until-segment', '1']), 1)
                self.assertEqual(len(api.posts), 1)
                state_path = work / 'segments/seg01/job/state.json'
                self.assertEqual(json.loads(state_path.read_text())['status'], 'SUCCESS')
                state_bytes = state_path.read_bytes()
                first = work / 'segments/seg01/published.mp4'
                stamp = first.stat().st_mtime_ns
                with patch.object(m, 'preflight_media', side_effect=AssertionError('completed job must not preflight sampling')):
                    self.assertEqual(m.main(command + ['--until-segment', '1']), 0)
                self.assertEqual(len(api.posts), 1, 'postprocess recovery must reuse the original successful prompt')
                self.assertEqual(state_path.read_bytes(), state_bytes)
                self.assertEqual(first.stat().st_mtime_ns, stamp)
                with patch.object(m, 'preflight_media', wraps=m.preflight_media) as preflight:
                    self.assertEqual(m.main(command + ['--until-segment', '2']), 0)
                    preflight.assert_called_once_with()
                self.assertEqual(len(api.posts), 2)
                self.assertEqual(m.main(command), 0)
                self.assertEqual(len(api.posts), 2)
                self.assertEqual(first.stat().st_mtime_ns, stamp)
                self.assertTrue((work / 'assemblies/through-seg02/final.mp4').is_file())
                binding_path = work / 'segments/seg02/predecessor.json'
                self.assertTrue(binding_path.is_file(), 'predecessor binding missing')
                binding = json.loads(binding_path.read_text())
                self.assertEqual(binding['verification_sha256'], m.digest(work / 'segments/seg01/verification.json'))
                self.assertEqual(binding['artifact_sha256']['video.latent'], m.digest(work / 'segments/seg01/video.latent'))
                # Same shape is not sufficient: the original predecessor bytes are bound.
                latent = work / 'segments/seg01/video.latent'
                original = latent.read_bytes()
                latent.write_bytes(original[:-1] + b'\x01')
                self.assertEqual(m.main(command), 1)
                self.assertEqual(len(api.posts), 2)
                latent.write_bytes(original)
                # Orphaned checkpoints/job files are not authorization to resample.
                state_path = work / 'segments/seg01/job/state.json'
                receipt_path = work / 'segments/seg01/verification.json'
                state_bytes, receipt_bytes = state_path.read_bytes(), receipt_path.read_bytes()
                state_path.unlink(); receipt_path.unlink()
                self.assertEqual(m.main(command + ['--until-segment', '1']), 1)
                self.assertEqual(len(api.posts), 2)
                state_path.write_bytes(state_bytes); receipt_path.write_bytes(receipt_bytes)
                # Changing durable input must fail rather than generating a new version.
                config = json.loads((work / 'run.json').read_text())
                (work / config['inputs']['character']['path']).write_bytes(b'changed')
                self.assertEqual(m.main(command), 1)
                self.assertEqual(len(api.posts), 2)

if __name__ == '__main__': unittest.main()
