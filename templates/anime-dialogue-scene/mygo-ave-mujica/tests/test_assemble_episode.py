import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/assemble_episode.py"
SPEC = importlib.util.spec_from_file_location("assemble_episode", SCRIPT)
assembler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assembler)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required for synthetic-media tests")
class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="episode-assembly-test-")
        cls.root = Path(cls.temp.name).resolve()
        (cls.root / "edit").mkdir()
        (cls.root / "runs").mkdir()
        cls.clips = []
        for i, frames in enumerate((24, 26)):
            path = cls.root / "runs" / f"s{i + 1}.mkv"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24",
                            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-frames:v", str(frames),
                            "-t", str(frames / 24), "-c:v", "ffv1", "-c:a", "pcm_s24le", str(path)], check=True)
            cls.clips.append({"id": f"s{i + 1}", "path": f"../runs/{path.name}", "sha256": assembler.file_sha(path),
                              "frames": frames, "visual_review": "accepted", "audio_review": "accepted"})

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.data = {"fps": 24, "width": 64, "height": 64, "segments": copy.deepcopy(self.clips)}
        self.manifest = self.root / "edit" / "selected-segments.json"
        self.output = self.root / "exports" / self._testMethodName

    def validate(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")
        return assembler.validate(self.manifest, self.root, self.output)

    def test_dry_run_then_execute_preserves_frames_samples_and_sources(self):
        plan, segments = self.validate()
        self.assertFalse(self.output.exists())
        self.assertEqual(plan["total_frames"], 50)
        self.assertEqual(plan["total_audio_samples"], 100000)
        result = assembler.execute(plan, segments, self.output)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["verification"]["frames"], 50)
        self.assertEqual(result["verification"]["audio_samples"], 100000)
        self.assertTrue(result["full_decode"])
        self.assertTrue((self.output / "master-native.mkv").is_file())
        self.assertFalse((self.output / "master-native.part.mkv").exists())
        for item in segments:
            self.assertEqual(assembler.file_sha(item["resolved_path"]), item["sha256"])
        with self.assertRaisesRegex(assembler.Invalid, "already exists"):
            self.validate()

    def test_wrong_sha_is_rejected(self):
        self.data["segments"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(assembler.Invalid, "SHA256 mismatch"):
            self.validate()
        self.assertFalse(self.output.exists())

    def test_wrong_frame_count_is_rejected(self):
        self.data["segments"][0]["frames"] += 1
        with self.assertRaisesRegex(assembler.Invalid, "frame count"):
            self.validate()

    def test_missing_content_review_is_rejected(self):
        for key in ("visual_review", "audio_review"):
            with self.subTest(key=key):
                self.data["segments"][0][key] = "pending"
                with self.assertRaisesRegex(assembler.Invalid, "reviews must be accepted"):
                    self.validate()
                self.data["segments"][0][key] = "accepted"

    def test_short_audio_cannot_be_hidden_with_padding(self):
        short = self.root / "runs" / "short-audio.mkv"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24:duration=1",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.1",
                        "-c:v", "ffv1", "-c:a", "pcm_s24le", str(short)], check=True)
        self.data["segments"][0].update(path="../runs/short-audio.mkv", sha256=assembler.file_sha(short))
        with self.assertRaisesRegex(assembler.Invalid, "Audio length"):
            self.validate()

    def test_input_cannot_escape_project(self):
        self.data["segments"][0]["path"] = "../../outside.mkv"
        with self.assertRaisesRegex(assembler.Invalid, "inside the project root"):
            self.validate()

    def test_story_plan_is_not_a_selected_segments_manifest(self):
        self.data = {"fps": 24, "width": 64, "height": 64, "shots": []}
        with self.assertRaisesRegex(assembler.Invalid, "not the episode story plan"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
