import hashlib
import json
from pathlib import Path
import unittest

RECIPE = Path(__file__).resolve().parents[1]


class HistoricalEvidenceTests(unittest.TestCase):
    def test_four_segments_have_original_prompt_and_exact_seed_strings(self):
        path = RECIPE / 'references/yaoguang-run.json'
        self.assertTrue(path.is_file(), 'Missing public historical run evidence')
        data = json.loads(path.read_text(encoding='utf-8'))
        segments = data['segments']
        self.assertEqual(len(segments), 4)
        self.assertEqual([s['seed'] for s in segments], [
            '214235573447273430', '1459903066845096071',
            '7850450784904972903', '8295737831123548902'])
        self.assertEqual([s['sample_frames'] for s in segments], [158, 192, 175, 175])
        self.assertEqual([s['visible_frames'] for s in segments], [158, 158, 141, 141])
        self.assertEqual([s['head_trim_frames'] for s in segments], [0, 22, 22, 22])
        self.assertEqual(len({s['prompt_id'] for s in segments}), 4)
        for segment in segments:
            prompt = (RECIPE / segment['prompt_file']).read_bytes()
            self.assertEqual(hashlib.sha256(prompt).hexdigest(), segment['prompt_sha256'])
            self.assertEqual(segment['prompt_sha256'],
                             '3a3c183c678220df4506354e76fe11647c12d856fbb4a08843408b56cedf64f2')
        self.assertEqual(data['settings']['ref_image_size']['value'], 'match')
        self.assertFalse(data['settings']['reference_audio_connected'])
        self.assertEqual(data['models']['audio_vae']['filename'], 'minimax_h3_audio_vae_fp32.safetensors')
        self.assertIsNone(data['models']['audio_vae']['historical_sha256'])
        self.assertFalse(data['verification']['new_gpu_inference'])
        self.assertNotRegex(path.read_text(encoding='utf-8'),
                            r'/(?:Users|home|data\d+)/[A-Za-z][\w.-]+')


if __name__ == '__main__':
    unittest.main()
