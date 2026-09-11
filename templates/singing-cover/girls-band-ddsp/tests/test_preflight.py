import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts/preflight.py"
SPEC = importlib.util.spec_from_file_location("cover_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


def artifact(path="model.pt", data=b"test bytes, not a model", size=True):
    return {
        "path": path,
        "bytes": len(data) if size else None,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b"test bytes, not a model"

    def test_all_eight_voices_have_paired_configs(self):
        expected = {
            "anon-12000", "mutsumi-20000", "nyamu-14000", "sakiko-20000",
            "soyo-14000", "taki-20000", "tomori-30000", "uika-28000",
        }
        manifest = json.loads((HERE.parent / "model-catalog/voices.json").read_text())
        self.assertEqual({voice["id"] for voice in manifest["voices"]}, expected)
        for voice in manifest["voices"]:
            with self.subTest(voice=voice["id"]):
                plan = preflight.build_plan(voice["id"])
                self.assertEqual(len(plan["artifacts"]), 12)
                self.assertEqual(voice["speaker_id"], 1)
                self.assertEqual(voice["training_steps"], int(voice["id"].rsplit("-", 1)[1]))
                self.assertEqual(voice["checkpoint"]["bytes"], 280285658)
                self.assertEqual(voice["config"]["bytes"], 1172)
                self.assertEqual(Path(voice["checkpoint"]["path"]).parent, Path(voice["config"]["path"]).parent)

    def test_ddsp_only_is_explicit_and_not_executable(self):
        plan = preflight.build_plan("tomori-30000", ddsp_only=True)
        self.assertEqual(len(plan["artifacts"]), 6)
        self.assertEqual(plan["status"], "plan-only")
        self.assertFalse(plan["executable"])
        self.assertEqual(plan["gpu_inference"], "not-run")
        self.assertEqual(plan["listening_review"], "pending")

    def test_unknown_voice_rejected(self):
        with self.assertRaises(ValueError):
            preflight.build_plan("unregistered")

    def test_matching_bytes_and_unknown_size(self):
        (self.root / "model.pt").write_bytes(self.data)
        for known_size in (True, False):
            result = preflight.check_artifacts(self.root, [artifact(size=known_size)])
            self.assertEqual(result[0]["status"], "match")

    def test_same_size_wrong_hash_rejected(self):
        (self.root / "model.pt").write_bytes(b"x" * len(self.data))
        self.assertEqual(preflight.check_artifacts(self.root, [artifact()])[0]["status"], "mismatch")

    def test_correct_hash_wrong_size_rejected(self):
        (self.root / "model.pt").write_bytes(self.data)
        item = artifact()
        item["bytes"] += 1
        self.assertEqual(preflight.check_artifacts(self.root, [item])[0]["status"], "mismatch")

    def test_missing_and_directory_rejected(self):
        self.assertEqual(preflight.check_artifacts(self.root, [artifact()])[0]["status"], "missing")
        (self.root / "model.pt").mkdir()
        self.assertEqual(preflight.check_artifacts(self.root, [artifact()])[0]["status"], "not-a-file")

    def test_unsafe_paths_rejected(self):
        for path in ("../model.pt", "/model.pt", "a/../model.pt", "a//b", "./b", "", "C:\\model.pt", "a\nb"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                preflight.validate_artifacts([artifact(path)])

    def test_invalid_hash_sizes_and_duplicates_rejected(self):
        for changes in ({"sha256": "abc"}, {"sha256": "A" * 64}, {"bytes": True}, {"bytes": -1}, {"bytes": 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                preflight.validate_artifacts([{**artifact(), **changes}])
        with self.assertRaises(ValueError):
            preflight.validate_artifacts([artifact(), artifact()])

    def test_symlink_escape_rejected_without_reading_target(self):
        model_root = self.root / "models"
        model_root.mkdir()
        outside = self.root / "outside.pt"
        outside.write_bytes(self.data)
        (model_root / "model.pt").symlink_to(outside)
        result = preflight.check_artifacts(model_root, [artifact()])[0]
        self.assertEqual(result["status"], "outside-model-root")
        self.assertNotIn("sha256", result)

    def test_internal_symlink_allowed(self):
        (self.root / "actual.pt").write_bytes(self.data)
        (self.root / "model.pt").symlink_to("actual.pt")
        self.assertEqual(preflight.check_artifacts(self.root, [artifact()])[0]["status"], "match")

    def test_broken_symlink_rejected(self):
        (self.root / "model.pt").symlink_to("missing.pt")
        self.assertEqual(preflight.check_artifacts(self.root, [artifact()])[0]["status"], "missing")

    def test_cli_plan_does_not_create_files(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--voice", "anon-12000"],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "plan-only")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cli_missing_models_nonzero_without_private_path(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = preflight.main(["--voice", "tomori-30000", "--check", "--model-root", str(self.root)])
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "byte-integrity-failed")
        self.assertTrue(all(item["status"] == "missing" for item in report["checks"]))
        self.assertNotIn(str(self.root), output.getvalue())

    def test_cli_matching_fixture_does_not_claim_inference(self):
        (self.root / "model.pt").write_bytes(self.data)
        plan = preflight.build_plan("tomori-30000")
        plan["artifacts"] = [artifact()]
        output = io.StringIO()
        with patch.object(preflight, "build_plan", return_value=plan):
            with contextlib.redirect_stdout(output):
                code = preflight.main(["--voice", "tomori-30000", "--check", "--model-root", str(self.root)])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "byte-integrity-checked")
        self.assertEqual(report["gpu_inference"], "not-run")
        self.assertEqual(report["listening_review"], "pending")
        self.assertFalse(report["executable"])

    def test_cli_unknown_voice_and_missing_root_rejected(self):
        for argv in (["--voice", "unknown"], ["--voice", "anon-12000", "--check", "--model-root", str(self.root / "missing")]):
            with self.subTest(argv=argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(preflight.main(argv), 2)

    def test_cli_check_root_pair_required(self):
        for extra in (["--check"], ["--model-root", str(self.root)]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    preflight.main(["--voice", "anon-12000", *extra])
                self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
