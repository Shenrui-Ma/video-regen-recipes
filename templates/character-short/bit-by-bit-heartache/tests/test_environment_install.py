import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

T = pathlib.Path(__file__).resolve().parents[1]

class InstallPlanTests(unittest.TestCase):
    def test_hash_gated_patch_application_requires_isolated_marker(self):
        import json, hashlib
        script = T / 'scripts/environment/apply_patches.py'
        self.assertTrue(script.exists(), 'Safe explicit patch helper missing')
        lock = json.loads((T/'references/dependencies.lock.json').read_text())
        with tempfile.TemporaryDirectory() as parent:
            root = pathlib.Path(parent)
            dests = [root/'ComfyUI/custom_nodes/H3MotionContextOfficial/nodes.py',
                     root/'.venv/lib/python3.10/site-packages/comfy_kitchen/backends/triton/quantization.py']
            origins = [T/'vendor/motion-context/upstream/nodes.py', T/'vendor/comfy-kitchen/upstream/quantization.py']
            for dest, source in zip(dests, origins):
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(source.read_bytes())
            def run(*flags):
                return subprocess.run([sys.executable, '-B', str(script), '--root', str(root), *flags], capture_output=True, text=True)
            self.assertNotEqual(run('--apply').returncode, 0)
            (root/'.heartache-isolated-install').write_text('heartache-new-environment-v1\n')
            before = [f.read_bytes() for f in dests]
            self.assertEqual(run().returncode, 0)
            self.assertEqual([f.read_bytes() for f in dests], before)
            applied = run('--apply')
            self.assertEqual(applied.returncode, 0, applied.stderr)
            expected = [lock['sources'][1]['patch']['after_sha256'], lock['int8_patch']['after_sha256']]
            self.assertEqual([hashlib.sha256(f.read_bytes()).hexdigest() for f in dests], expected)
            self.assertEqual(run('--apply').returncode, 0)
            dests[1].write_text('unknown source')
            self.assertNotEqual(run('--apply').returncode, 0)
            self.assertEqual(dests[1].read_text(), 'unknown source')

    def test_installer_only_prints_a_reviewable_plan(self):
        script = T / 'scripts/environment/install.py'
        self.assertTrue(script.exists(), 'No installer plan CLI')
        with tempfile.TemporaryDirectory() as parent:
            target = pathlib.Path(parent) / 'new-environment'
            r = subprocess.run([sys.executable, '-B', str(script), '--target', str(target)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('--require-hashes', r.stdout)
            self.assertIn('apply_patches.py', r.stdout)
            self.assertNotIn('--disable-all-custom-nodes', r.stdout)
            self.assertFalse(target.exists(), 'Printing a plan must not install anything')
