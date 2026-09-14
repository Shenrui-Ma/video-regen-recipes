import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

RUNTIME = Path(__file__).resolve().parents[1] / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))

class RunnerTests(unittest.TestCase):
    def test_lost_submit_response_never_reposts(self):
        self.assertTrue((RUNTIME / 'run_segment.py').exists(), 'portable runner missing')
        r = importlib.import_module('run_segment')
        class API:
            host = 'http://localhost:8188'
            interval = 0
            posts = 0
            def request(self, path, body=None):
                if path == '/object_info': return {'Example': {}}
                if path == '/queue': return {'queue_running': [], 'queue_pending': []}
                if path.startswith('/history/'): return {}
                if path == '/prompt':
                    self.posts += 1
                    raise r.RunnerError('HTTP_IO_FAILED')
                raise AssertionError(path)
        with tempfile.TemporaryDirectory() as tmp:
            api = API()
            graph = {'1': {'class_type': 'Example', 'inputs': {}}}
            first, code = r.run(api, graph, Path(tmp), False)
            self.assertEqual(first['status'], 'AMBIGUOUS')
            second, code = r.run(api, graph, Path(tmp), False)
            self.assertEqual(second['status'], 'AMBIGUOUS')
            self.assertEqual(api.posts, 1)
            with self.assertRaises(r.RunnerError):
                r.run(api, {'2': {'class_type': 'Example', 'inputs': {}}}, Path(tmp), False)

if __name__ == '__main__': unittest.main()
