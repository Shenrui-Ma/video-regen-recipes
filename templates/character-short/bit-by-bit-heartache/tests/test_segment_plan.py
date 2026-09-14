import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SegmentPlanTests(unittest.TestCase):
    def test_capacity_controls_count_and_preserves_timeline(self):
        script = ROOT / 'scripts/plan_segments.py'
        self.assertTrue(script.is_file(), 'Missing hardware-capacity segment planner')
        spec = importlib.util.spec_from_file_location('segment_plan', script)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        short = mod.plan_segments(577, 90, 22)
        long = mod.plan_segments(577, 243, 22)
        self.assertGreater(len(short), len(long))
        for rows, cap in [(short, 90), (long, 243)]:
            self.assertEqual(rows[0]['timeline_start'], 0)
            self.assertEqual(rows[-1]['timeline_end'], 577)
            self.assertEqual(sum(r['visible_frames'] for r in rows), 577)
            for i, row in enumerate(rows):
                self.assertLessEqual(row['sample_frames'], cap)
                self.assertEqual((row['sample_frames'] - 5) % 17, 0)
                self.assertEqual(row['head_trim_frames'], 0 if i == 0 else 22)
                self.assertEqual(row['publish_end'], row['head_trim_frames'] + row['visible_frames'])
                if i:
                    self.assertEqual(row['timeline_start'], rows[i-1]['timeline_end'])
                    self.assertEqual(row['predecessor'], i)

    def test_cli_marks_manual_capacity_as_unverified(self):
        import json
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/plan_segments.py'),
                                 '--frames', '577', '--max-sample-frames', '90'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), 'CLI must emit a plan')
        data = json.loads(result.stdout)
        self.assertEqual(data['capacity_basis'], 'agent-supplied; calibration-required')
        self.assertFalse(data['inference_verified'])
        self.assertEqual(data['segment_count'], len(data['segments']))
        self.assertIn('gpus', data['hardware'])

    def test_recipe_keeps_four_segments_only_as_history(self):
        import json
        profile = json.loads((ROOT / 'profile.json').read_text())
        self.assertEqual(profile['generation'].get('segment_policy'), 'hardware-calibrated')
        self.assertNotIn('visible_frames', profile['generation'])
        self.assertEqual(profile['historical_generation']['visible_frames'], [158, 158, 141, 141])
        self.assertNotIn('串行生成四段', (ROOT / 'SKILL.md').read_text())

    def test_invalid_frame_counts_are_rejected(self):
        spec = importlib.util.spec_from_file_location('segment_plan', ROOT / 'scripts/plan_segments.py')
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with self.assertRaises(ValueError):
            mod.plan_segments(0, 90, 22)
        for args in [(577, 22, 22), (1, 4, 22), (10, 90, -1), (1.5, 90, 22), (True, 90, 22)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                mod.plan_segments(*args)
        self.assertEqual(len(mod.plan_segments(1, 5, 22)), 1)


if __name__ == '__main__':
    unittest.main()
