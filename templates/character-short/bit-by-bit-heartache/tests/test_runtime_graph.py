import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

T = Path(__file__).resolve().parents[1]
RUNTIME = T / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))
import graphs  # noqa: E402


class GraphLockTests(unittest.TestCase):
    def test_lock_pins_both_graphs_to_a_commit(self):
        lock = json.loads((T / 'references/workflow.lock.json').read_text())
        names = {row['name'] for row in lock['graphs']}
        self.assertEqual(names, {'first', 'continue'})
        self.assertEqual(lock['workflow_id'], 'h3-ref2va-core-continuation')
        for row in lock['graphs']:
            self.assertEqual(len(row['sha256']), 64)
            self.assertTrue(row['url'].startswith('https://raw.githubusercontent.com/Shenrui-Ma/shenrui-comfyui-toolkit/'))
            self.assertIn(lock['commit'], row['url'])

    def test_this_repository_no_longer_ships_runtime_graphs(self):
        for name in ('first.api.json', 'continue.api.json'):
            self.assertFalse((T / 'workflows' / name).exists(), name + ' should come from the lock')

    def test_unknown_graph_name_is_rejected(self):
        with self.assertRaises(ValueError):
            graphs.load_graph('does-not-exist', cache_dir=tempfile.mkdtemp())


class BindTests(unittest.TestCase):
    def test_bind_replaces_whole_value_tokens_with_typed_values(self):
        graph = {'5': {'inputs': {'length': '{{sample_frames}}', 'width': '{{width}}'}},
                 '10': {'inputs': {'seed': '{{seed}}'}}}
        bound = graphs.bind(graph, {'sample_frames': 107, 'width': 1344, 'seed': 42})
        self.assertEqual(bound['5']['inputs']['length'], 107)
        self.assertIs(type(bound['5']['inputs']['length']), int)
        self.assertEqual(bound['10']['inputs']['seed'], 42)

    def test_bind_rejects_embedded_or_missing_placeholders(self):
        with self.assertRaises(ValueError):
            graphs.bind({'1': {'inputs': {'prompt': 'prefix {{prompt}} suffix'}}}, {'prompt': 'x'})
        with self.assertRaises(ValueError):
            graphs.bind({'1': {'inputs': {'prompt': '{{prompt}}'}}}, {})


class BindingTests(unittest.TestCase):
    def _pinned(self):
        try:
            cache = tempfile.mkdtemp()
            return {name: graphs.load_graph(name, cache_dir=cache) for name in ('first', 'continue')}
        except (urllib.error.URLError, OSError) as exc:
            self.skipTest('pinned toolkit graphs unavailable offline: ' + type(exc).__name__)

    def test_build_binds_plan_rows_against_the_pinned_graphs(self):
        pinned = self._pinned()
        cache = tempfile.mkdtemp()
        rows = graphs.plan_segments(577, 107, 22)
        for row in rows:
            graph = graphs.build(row, 'session/character.png', 'session/ref.mp4',
                                 'A red-haired person wearing a green coat', 123,
                                 'session/video.latent', 'session/audio.latent', 'session',
                                 cache_dir=cache)
            self.assertEqual(graph['5']['inputs']['length'] % 17, 5)
            self.assertEqual(graph['54']['inputs']['length'], row['visible_frames'])
            self.assertEqual(graph['21']['inputs']['image'], 'session/character.png')
            self.assertIn('A red-haired person wearing a green coat', graph['5']['inputs']['prompt'])
            self.assertNotIn('Yaoguang', graph['5']['inputs']['prompt'])
            graphs.validate_graph(graph)
            self.assertEqual(graphs.from_editor(graphs.to_editor(graph)), graph)
        self.assertEqual(sum(r['visible_frames'] for r in rows), 577)
        self.assertEqual(graphs.plan_segments(577, 158, 22)[0]['sample_frames'], 158)

    def test_continuation_row_requires_both_latents(self):
        self._pinned()
        cache = tempfile.mkdtemp()
        row = graphs.plan_segments(577, 107, 22)[1]
        with self.assertRaises(ValueError):
            graphs.build(row, 'session/character.png', 'session/ref.mp4', 'desc', 123,
                         None, None, 'session', cache_dir=cache)

    def test_published_checkpoint_structure_is_preserved(self):
        pinned = self._pinned()
        for graph in pinned.values():
            self.assertEqual(graph['60']['inputs']['av_latent'], ['10', 0])
            self.assertEqual(graph['61']['class_type'], 'SaveLatent')
            self.assertEqual(graph['62']['class_type'], 'SaveLatent')
            self.assertEqual(graph['63']['inputs'],
                             {'video_latent': ['61', 0], 'audio_latent': ['62', 0]})
        cont = pinned['continue']
        self.assertEqual(cont['51']['class_type'], 'LoadLatent')
        self.assertEqual(cont['53']['inputs']['context_latent'], ['50', 0])
        self.assertEqual(cont['54']['inputs']['batch_index'], ['53', 1])
        self.assertNotIn('53', pinned['first'])


if __name__ == '__main__':
    unittest.main()
