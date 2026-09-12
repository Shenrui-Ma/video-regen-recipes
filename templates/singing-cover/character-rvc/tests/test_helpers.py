import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location("character_rvc_" + name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load("run_guard")
filelist = load("build_filelist")


class HelpersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def put(self, relative, content=b"fixture-not-real-media"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def call(self, module, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return module.main(list(map(str, args)))

    def fixture(self):
        for name in ("0_1", "0_2"):
            for directory, suffix in filelist.MODALITIES.values():
                self.put("exp/" + directory + "/" + name + suffix)
        for directory, name in (("0_gt_wavs", "mute48k.wav"), ("3_feature768", "mute.npy"),
                                ("2a_f0", "mute.wav.npy"), ("2b-f0nsf", "mute.wav.npy")):
            self.put("mute/" + directory + "/" + name)

    def build_args(self):
        return ["--experiment", self.root / "exp", "--mute-root", self.root / "mute",
                "--output", self.root / "filelist.txt", "--report", self.root / "report.json"]

    def test_intersection_mute_counts_determinism_and_spec_cache_ignored(self):
        self.fixture()
        self.put("exp/0_gt_wavs/0_1.spec.pt")
        text, report = filelist.build(self.root / "exp", self.root / "mute")
        self.assertEqual((report["character_rows"], report["mute_rows"], report["total_rows"]), (2, 2, 4))
        self.assertEqual(text.splitlines()[-1], text.splitlines()[-2])
        self.assertTrue(all(len(row.split("|")) == 5 for row in text.splitlines()))
        self.assertEqual(text, filelist.build(self.root / "exp", self.root / "mute")[0])
        self.assertEqual(self.call(filelist, self.build_args()), 0)
        self.assertEqual(self.call(filelist, self.build_args()), 2)

    def test_incomplete_requires_explicit_acceptance_and_lists_orphans(self):
        self.fixture()
        self.put("exp/3_feature768/0_61.npy")
        self.put("exp/0_gt_wavs/0_61.wav")
        self.assertEqual(self.call(filelist, self.build_args()), 2)
        self.assertFalse((self.root / "filelist.txt").exists())
        self.assertEqual(self.call(filelist, self.build_args() + ["--allow-incomplete"]), 0)
        report = json.loads((self.root / "report.json").read_text())
        self.assertEqual(report["modality_counts"]["feature768"], 3)
        self.assertEqual(report["excluded_missing_modalities"]["0_61"], ["f0", "f0nsf"])

    def test_empty_file_empty_intersection_and_bad_path_rejected(self):
        self.fixture()
        self.put("exp/0_gt_wavs/0_1.wav", b"")
        self.assertEqual(self.call(filelist, self.build_args()), 2)
        self.put("exp/0_gt_wavs/0_1.wav")
        self.put("exp/3_feature768/bad|id.npy")
        self.assertEqual(self.call(filelist, self.build_args()), 2)
        (self.root / "exp/3_feature768/bad|id.npy").unlink()
        for path in (self.root / "exp/2a_f0").iterdir():
            path.unlink()
        self.assertEqual(self.call(filelist, self.build_args() + ["--allow-incomplete"]), 2)

    def test_missing_mute_symlinks_and_same_output_rejected(self):
        self.fixture()
        mute = self.root / "mute/3_feature768/mute.npy"
        mute.unlink()
        self.assertEqual(self.call(filelist, self.build_args()), 2)
        mute.symlink_to(self.root / "exp/3_feature768/0_1.npy")
        self.assertEqual(self.call(filelist, self.build_args()), 2)
        mute.unlink()
        mute.write_bytes(b"fixture")
        args = self.build_args()
        args[-1] = args[-3]
        self.assertEqual(self.call(filelist, args), 2)

    def spec(self):
        self.put("features/a.npy", b"abc")
        spec = {"schema_version": 1, "parameters": {"version": "v2", "index_rate": 0.65},
                "resources": {"features": "features"}}
        path = self.root / "spec.json"
        path.write_text(json.dumps(spec))
        return path

    def test_guard_changed_bytes_even_same_size_and_receipt_tamper(self):
        spec = self.spec()
        receipt = self.root / "receipt.json"
        self.assertEqual(self.call(guard, ["snapshot", "--spec", spec, "--output", receipt]), 0)
        self.assertEqual(self.call(guard, ["check", "--spec", spec, "--receipt", receipt]), 0)
        self.put("features/a.npy", b"def")
        self.assertEqual(self.call(guard, ["check", "--spec", spec, "--receipt", receipt]), 1)
        self.put("features/a.npy", b"abc")
        saved = json.loads(receipt.read_text())
        saved["fingerprint_sha256"] = "0" * 64
        receipt.write_text(json.dumps(saved))
        self.assertEqual(self.call(guard, ["check", "--spec", spec, "--receipt", receipt]), 1)

    def test_guard_membership_and_parameters(self):
        spec = self.spec()
        receipt = self.root / "receipt.json"
        original = guard.fingerprint(spec, receipt)
        added = self.put("features/b.npy")
        self.assertNotEqual(original, guard.fingerprint(spec, receipt))
        added.unlink()
        self.assertEqual(original, guard.fingerprint(spec, receipt))
        obj = json.loads(spec.read_text())
        obj["parameters"]["index_rate"] = 0.55
        spec.write_text(json.dumps(obj))
        self.assertNotEqual(original, guard.fingerprint(spec, receipt))
        (self.root / "features/a.npy").unlink()
        with self.assertRaises(ValueError):
            guard.fingerprint(spec, receipt)

    def test_guard_no_overwrite_self_reference_or_links(self):
        spec = self.spec()
        receipt = self.root / "receipt.json"
        self.assertEqual(self.call(guard, ["snapshot", "--spec", spec, "--output", receipt]), 0)
        self.assertEqual(self.call(guard, ["snapshot", "--spec", spec, "--output", receipt]), 2)
        with self.assertRaises(ValueError):
            guard.fingerprint(spec, self.root / "features/receipt.json")
        (self.root / "features/link.npy").symlink_to(self.root / "features/a.npy")
        with self.assertRaises(ValueError):
            guard.fingerprint(spec, receipt)

    def test_guard_missing_resource_and_invalid_spec(self):
        spec = self.spec()
        (self.root / "features/a.npy").unlink()
        self.assertEqual(self.call(guard, ["snapshot", "--spec", spec, "--output", self.root / "r.json"]), 2)
        spec.write_text("[]")
        self.assertEqual(self.call(guard, ["snapshot", "--spec", spec, "--output", self.root / "r.json"]), 2)


if __name__ == "__main__":
    unittest.main()
