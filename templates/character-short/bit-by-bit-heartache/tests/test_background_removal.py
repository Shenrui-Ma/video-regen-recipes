"""Offline checks for the optional RMBG API graph; no model or GPU execution."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BackgroundRemovalTests(unittest.TestCase):
    def test_optional_model_manifest_pins_files_without_license_assumption(self):
        path = ROOT / 'references/rmbg-model-manifest.json'
        self.assertTrue(path.is_file(), 'Optional model dependency manifest is missing')
        manifest = json.loads(path.read_text())
        self.assertTrue(manifest['optional'])
        self.assertFalse(manifest['bundled'])
        self.assertEqual(manifest['model']['repo_id'], '1038lab/RMBG-2.0')
        self.assertEqual(manifest['model']['revision'], '1cd4787601caeb4c8e826dba7ea8e2163b5208df')
        self.assertEqual(manifest['model']['relative_directory'], 'models/RMBG/RMBG-2.0')
        self.assertEqual(set(manifest['model']['files']), {'config.json', 'birefnet.py', 'BiRefNet_config.py', 'model.safetensors'})
        self.assertEqual(manifest['model']['files']['model.safetensors']['sha256'],
                         '566ed80c3d95f87ada6864d4cbe2290a1c5eb1c7bb0b123e984f60f76b02c3a7')
        for details in manifest['model']['files'].values():
            self.assertRegex(details['sha256'], r'^[0-9a-f]{64}$')
            self.assertGreater(details['bytes'], 0)
        self.assertEqual(manifest['node']['revision'], 'bd509b4750c81221b938684489c87187b0172208')
        self.assertFalse(manifest['node']['clean_install_inference_verified'])
        self.assertTrue(manifest['license']['upstream_confirmation_required'])
        self.assertNotIn('Apache', json.dumps(manifest['license']))

    def test_optional_graph_retains_alpha_and_mask_without_generation(self):
        path = ROOT / 'workflows/rmbg.api.json'
        self.assertTrue(path.is_file(), 'Portable optional RMBG graph is missing')
        graph = json.loads(path.read_text())
        self.assertEqual(set(graph), {'1', '2', '3', '4'})
        self.assertEqual(graph['1'], {'class_type': 'LoadImage', 'inputs': {'image': '__CHARACTER_IMAGE__'}})
        self.assertEqual(graph['2'], {
            'class_type': 'RMBG', 'inputs': {
                'image': ['1', 0], 'model': 'RMBG-2.0', 'sensitivity': 1.0,
                'process_res': 1024, 'mask_blur': 0, 'mask_offset': 0,
                'invert_output': False, 'refine_foreground': False,
                'background': 'Alpha', 'background_color': '#FFFFFF',
            },
        })
        # Slot 1 is MASK; slot 2 is the saveable MASK_IMAGE, not the cutout.
        self.assertEqual(graph['3'], {'class_type': 'SaveImage', 'inputs': {
            'images': ['2', 0], 'filename_prefix': '__OUTPUT_PREFIX__/alpha'}})
        self.assertEqual(graph['4'], {'class_type': 'SaveImage', 'inputs': {
            'images': ['2', 2], 'filename_prefix': '__OUTPUT_PREFIX__/mask'}})
        # The opt-in graph must not become a dependency of existing H3 graphs.
        for other in (ROOT / 'workflows').glob('*.api.json'):
            if other != path:
                self.assertNotIn('"class_type": "RMBG"', other.read_text())


if __name__ == '__main__':
    unittest.main()
