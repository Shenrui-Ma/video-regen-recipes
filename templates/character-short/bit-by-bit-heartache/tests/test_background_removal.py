"""Offline checks for the optional RMBG step.

This template no longer carries the background-removal graph: it references the
toolkit package instead. These tests keep the pointer honest and make sure the
cut-out step stays out of the H3 graphs. No model or GPU execution.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PIN = '667eafd'


class BackgroundRemovalTests(unittest.TestCase):
    def test_template_no_longer_carries_the_rmbg_graph(self):
        for stale in ('workflows/rmbg.api.json',
                      'references/rmbg-models.json',
                      'references/rmbg-model-manifest.json'):
            self.assertFalse((ROOT / stale).is_file(), stale)

    def test_environment_lock_points_at_the_optional_workflow(self):
        lock = json.loads((ROOT / 'references/environment.lock.json').read_text())
        rows = lock['optional_workflows']
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['id'], 'rmbg-2-character-alpha')
        self.assertEqual(row['path'], 'workflows/images/rmbg-2-alpha')
        self.assertIn(PIN, row['tree_url'])
        self.assertIn('去背景', row['purpose'])

    def test_guide_references_the_toolkit_package_and_keeps_the_rules(self):
        text = (ROOT / 'references/background-removal.md').read_text()
        self.assertIn('workflows/images/rmbg-2-alpha', text)
        self.assertNotIn('workflows/rmbg.api.json', text)
        # 槽位语义与白底合成必须留下：丢掉任何一条都会误导使用者
        for kept in ('输出0', '输出2', 'character-white', '#FFFFFF'):
            self.assertIn(kept, text, kept)
        # 节点许可与模型授权是两件事
        self.assertIn('GPL-3.0', text)
        self.assertIn('BRIA', text)
        # 占位符名要与 toolkit 的图一致
        self.assertIn('{{input_image}}', text)
        self.assertIn('{{alpha_prefix}}', text)
        self.assertIn('{{mask_prefix}}', text)

    def test_character_input_points_at_the_toolkit_package(self):
        text = (ROOT / 'references/character-input.md').read_text()
        self.assertIn('rmbg-2-alpha', text)
        self.assertNotIn('workflows/rmbg.api.json', text)

    def test_rmbg_is_not_a_dependency_of_the_h3_graphs(self):
        graphs = list((ROOT / 'workflows').glob('*.api.json')) + list((ROOT / 'workflows').glob('*.editor.json'))
        self.assertTrue(graphs, 'expected the H3 graphs to be present')
        for other in graphs:
            self.assertNotIn('"class_type": "RMBG"', other.read_text(), other.name)


if __name__ == '__main__':
    unittest.main()
