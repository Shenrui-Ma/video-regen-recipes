"""CPU-only checks of the FFmpeg selected by this process's PATH."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'scripts/runtime'
sys.path.insert(0, str(RUNTIME))


class MediaPreflightTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'executable PATH fixture needs POSIX')
    def test_path_encoder_failure_is_actionable_not_a_capability_listing(self):
        media = importlib.import_module('media')
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / 'ffmpeg'
            log = Path(tmp) / 'arguments.json'
            tool.write_text('#!' + sys.executable + '\nimport json, sys\n'
                            + 'open(' + repr(str(log)) + ', "w").write(json.dumps(sys.argv[1:]))\n'
                            + 'print("AAC encoder is experimental", file=sys.stderr)\nsys.exit(1)\n')
            tool.chmod(0o755)
            with patch.dict(os.environ, {'PATH': tmp + os.pathsep + os.environ['PATH']}):
                with self.assertRaisesRegex(ValueError, 'FFMPEG_AAC_PREFLIGHT_FAILED.*experimental.*PATH'):
                    media.preflight_media()
            args = json.loads(log.read_text())
            self.assertIn('aac', args)
            self.assertNotIn('-encoders', args)
            self.assertNotIn('-strict', args)
            self.assertFalse(Path(args[-1]).parent.exists(), 'preflight temporary files leaked')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg needed')
    def test_real_aac_encode_probe_and_decode(self):
        media = importlib.import_module('media')
        self.assertTrue(hasattr(media, 'preflight_media'), 'actual AAC preflight missing')
        receipt = media.preflight_media()
        self.assertEqual(receipt['codec_name'], 'aac')
        self.assertEqual(receipt['sample_rate'], '44100')
        self.assertEqual(receipt['channels'], 2)
        self.assertTrue(receipt['full_decode'])
        self.assertFalse(receipt['inference'])


if __name__ == '__main__':
    unittest.main()
