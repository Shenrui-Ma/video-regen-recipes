import importlib.util
from pathlib import Path
import unittest

RECIPE = Path(__file__).resolve().parents[1]
SCRIPT = RECIPE / 'scripts/prepare_driver.py'


class DriverContractTests(unittest.TestCase):
    def load_helper(self):
        self.assertTrue(SCRIPT.is_file(), 'Missing checked historical-driver preparation helper')
        spec = importlib.util.spec_from_file_location('prepare_driver', SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_rejects_578_frame_reconstruction_instead_of_silently_trimming(self):
        m = self.load_helper()
        good = {'frames': 577, 'width': 1344, 'height': 768, 'fps': '24/1'}
        m.validate_master(good, m.EXPECTED_SHA256)
        for key, value in [('frames', 578), ('width', 1280), ('fps', '25/1')]:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    m.validate_master(dict(good, **{key: value}), m.EXPECTED_SHA256)
        with self.assertRaises(ValueError):
            m.validate_master(good, '0' * 64)

    def test_split_uses_historical_intervals_and_does_not_copy_reference_audio(self):
        m = self.load_helper()
        self.assertEqual(m.RANGES, [(0, 158), (151, 309), (302, 443), (436, 577)])
        for start, end in m.RANGES:
            args = m.segment_command('ffmpeg', Path('space in/input.mp4'), Path('out.mp4'), start, end)
            self.assertIn('-n', args)
            self.assertNotIn('-y', args)
            self.assertIn('-an', args)
            self.assertIn(f'trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS', args)
            self.assertIn('space in/input.mp4', args)
            self.assertEqual(args[args.index('-crf') + 1], '0')


if __name__ == '__main__':
    unittest.main()
