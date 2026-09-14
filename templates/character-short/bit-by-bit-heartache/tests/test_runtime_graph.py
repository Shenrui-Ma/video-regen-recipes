import importlib.util
import json
from pathlib import Path
import sys
import unittest

T = Path(__file__).resolve().parents[1]
RUNTIME = T / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))

class GraphTests(unittest.TestCase):
    def test_first_and_continue_public_checkpoint(self):
        for name in ('first', 'continue'):
            path = T / 'workflows' / (name + '.api.json')
            self.assertTrue(path.exists(), 'portable API workflow missing')
            g = json.loads(path.read_text())
            self.assertEqual(g['60']['inputs']['av_latent'], ['10', 0])
            self.assertEqual(g['61']['class_type'], 'SaveLatent')
            self.assertEqual(g['62']['class_type'], 'SaveLatent')
            self.assertEqual(g['63']['inputs'], {'video_latent': ['61', 0], 'audio_latent': ['62', 0]})
            self.assertEqual(g['11']['inputs']['samples'], ['63', 0])
            self.assertEqual(g['5']['inputs']['ref_images.ref_image_0'], ['21', 0])
            self.assertNotIn('audio', g['13']['inputs'])
            self.assertFalse(any('MiniMaxH3AVLatent' in n['class_type'] or n['class_type'].startswith('TrimMiniMax') for n in g.values()))
            if name == 'continue':
                self.assertEqual(g['51']['class_type'], 'LoadLatent')
                self.assertEqual(g['52']['class_type'], 'LoadLatent')
                self.assertEqual(g['53']['inputs']['context_latent'], ['50', 0])
                self.assertEqual(g['54']['inputs']['batch_index'], ['53', 1])
            else:
                self.assertNotIn('53', g)
                self.assertEqual(g['54']['inputs']['batch_index'], 0)

class BindingTests(unittest.TestCase):
    def test_plan_binding_and_editor_roundtrip(self):
        self.assertTrue((RUNTIME / 'graphs.py').exists(), 'runtime graph binder missing')
        import graphs
        rows = graphs.plan_segments(577, 107, 22)
        for row in rows:
            graph = graphs.build(row, 'session/character.png', 'session/ref.mp4',
                                 'A red-haired person wearing a green coat', 123,
                                 'session/video.latent', 'session/audio.latent', 'session')
            self.assertEqual(graph['5']['inputs']['length'] % 17, 5)
            self.assertEqual(graph['54']['inputs']['length'], row['visible_frames'])
            self.assertEqual(graph['21']['inputs']['image'], 'session/character.png')
            self.assertIn('A red-haired person wearing a green coat', graph['5']['inputs']['prompt'])
            self.assertNotIn('Yaoguang', graph['5']['inputs']['prompt'])
            graphs.validate_graph(graph)
            self.assertEqual(graphs.from_editor(graphs.to_editor(graph)), graph)
        self.assertEqual(sum(r['visible_frames'] for r in rows), 577)
        self.assertEqual(graphs.plan_segments(577, 158, 22)[0]['sample_frames'], 158)
        bad = json.loads((T / 'workflows/continue.api.json').read_text())
        bad['54']['inputs']['batch_index'] = ['53', 0]
        with self.assertRaises(ValueError):
            graphs.validate_graph(bad)

if __name__ == '__main__':
    unittest.main()
