import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ReleaseReviewTests(unittest.TestCase):
    def test_release_exposes_reference_and_media_guides(self):
        profile = json.loads((ROOT / 'profile.json').read_text())
        for key in ('character_preprocessing', 'media_preflight', 'first_segment_validation'):
            self.assertIn(key, profile['files'])
            self.assertTrue((ROOT / profile['files'][key]).is_file())
        self.assertEqual(profile['runtime']['distribution_mode'], 'portable-no-media')

    def test_current_evidence_keeps_validation_scopes_separate(self):
        path = ROOT / 'references/first-segment-validation.json'
        self.assertTrue(path.exists())
        data = json.loads(path.read_text())
        self.assertTrue(data['existing_environment_first_segment_verified'])
        self.assertFalse(data['clean_install_inference_verified'])
        self.assertFalse(data['full_new_character_continuation_verified'])
        self.assertEqual(len(data['runs']), 2)
        for run in data['runs']:
            self.assertEqual(run['frames'], 107)
            self.assertEqual(run['fps'], 24)
            self.assertTrue(run['full_decode'])
            self.assertEqual(len(run['video_sha256']), 64)
        self.assertIn('references/dependencies.lock.json', (ROOT / 'LICENSES.md').read_text())
        self.assertNotIn('references/environment.lock.json', (ROOT / 'LICENSES.md').read_text())

if __name__ == '__main__':
    unittest.main()
