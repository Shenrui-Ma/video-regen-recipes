import importlib.util
import pathlib
import tempfile
import unittest

T = pathlib.Path(__file__).resolve().parents[1]

class ModelPlanTests(unittest.TestCase):
    def test_model_command_plan_has_immutable_urls_hashes_and_no_download(self):
        import subprocess, sys, json
        script = T/'scripts/environment/model_commands.py'
        self.assertTrue(script.exists(), 'Model acquisition commands missing')
        with tempfile.TemporaryDirectory() as parent:
            root = pathlib.Path(parent)/'ComfyUI'
            r = subprocess.run([sys.executable, '-B', str(script), '--comfy-root', str(root)], capture_output=True,text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            lock = json.loads((T/'references/dependencies.lock.json').read_text())
            for model in lock['models']:
                self.assertIn(model['url'], r.stdout)
                self.assertIn(model['sha256'], r.stdout)
            self.assertIn('I_ACCEPT_MINIMAX_H3_LICENSE', r.stdout)
            self.assertFalse(root.exists())
