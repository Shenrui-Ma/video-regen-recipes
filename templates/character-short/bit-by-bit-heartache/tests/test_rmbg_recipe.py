import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class RmbgRecipeTests(unittest.TestCase):
    def test_optional_graph_saves_alpha_and_mask_image(self):
        graph=json.loads((ROOT/'workflows/rmbg.api.json').read_text())
        self.assertEqual(set(n['class_type'] for n in graph.values()), {'LoadImage','RMBG','SaveImage'})
        self.assertEqual(graph['2']['inputs']['background'],'Alpha')
        self.assertEqual(graph['3']['inputs']['images'],['2',0])
        self.assertEqual(graph['4']['inputs']['images'],['2',2])
        self.assertIn('__CHARACTER_IMAGE__',graph['1']['inputs']['image'])
    def test_optional_model_urls_and_documented_hashes_agree(self):
        models=json.loads((ROOT/'references/rmbg-models.json').read_text())
        evidence=json.loads((ROOT/'references/rmbg-model-manifest.json').read_text())
        self.assertTrue(models['optional'])
        self.assertEqual(len(models['assets']),4)
        for row in models['assets']:
            self.assertFalse(row['required'])
            self.assertIn(evidence['model']['revision'],row['url'])
            self.assertEqual(evidence['model']['files'][Path(row['path']).name],{k:row[k] for k in ['bytes','sha256']})
