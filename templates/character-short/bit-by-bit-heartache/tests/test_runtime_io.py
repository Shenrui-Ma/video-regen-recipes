import importlib
from pathlib import Path
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))

class IOTests(unittest.TestCase):
    def test_history_paths_and_pair_staging(self):
        self.assertTrue((RUNTIME / 'local_io.py').exists(), 'safe local history staging missing')
        m = importlib.import_module('local_io')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            output = root / 'comfy/output'; output.mkdir(parents=True)
            entry = {'filename': 'v.latent', 'subfolder': 'run', 'type': 'output'}
            (output / 'run').mkdir()
            (output / 'run/v.latent').write_bytes(b'fixture-video-not-real-latent')
            outputs = {'61': {'latents': [entry]}}
            self.assertEqual(m.history_file(outputs, '61', '.latent', root / 'comfy'), output / 'run/v.latent')
            for replacement in [{'filename': '../v.latent'}, {'filename': 'x\\v.latent'}, {'subfolder': '../escape'}, {'subfolder': '/absolute'}, {'type': 'input'}, {'filename': 'C:v.latent'}]:
                with self.assertRaises(ValueError):
                    m.history_file({'61': {'latents': [{**entry, **replacement}]}}, '61', '.latent', root / 'comfy')
            outside = root / 'outside'; outside.mkdir()
            (outside / 'v.latent').write_bytes(b'outside')
            (output / 'link').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                m.history_file({'61': {'latents': [{**entry, 'subfolder': 'link'}]}}, '61', '.latent', root / 'comfy')
            destination = root / 'comfy/input/run/v.latent'
            digest = m.copy_verified(output / 'run/v.latent', destination)
            self.assertEqual(digest, m.digest(destination))
            self.assertEqual(m.copy_verified(output / 'run/v.latent', destination), digest)
            destination.write_bytes(b'changed')
            with self.assertRaises(ValueError): m.copy_verified(output / 'run/v.latent', destination)

if __name__ == '__main__': unittest.main()
