import base64
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zlib

spec = importlib.util.spec_from_file_location("image2_generate", Path(__file__).parents[1] / "scripts/generate.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return gen.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")


def response():
    return {"id": "response-fixture", "status": "completed", "output": [{"id": "image-fixture", "type": "image_generation_call", "status": "completed", "result": base64.b64encode(png()).decode()}]}


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "prompt.txt").write_text("Create one scene using Image 1 for identity.")
        (self.root / "character.png").write_bytes(png())
        self.task = self.root / "task.json"
        self.task.write_text(json.dumps({"prompt_file": "prompt.txt", "references": [{"path": "character.png", "role": "identity"}], "size": "1536x1024"}))
        self.out = self.root / "run"

    def test_offline_plan_embeds_real_bytes_and_high(self):
        body, manifest, _ = gen.build_request(self.task, "language-model-fixture")
        req = json.loads(body)
        self.assertEqual(req["tools"][0]["quality"], "high")
        self.assertEqual(req["tools"][0]["model"], "gpt-image-2")
        self.assertEqual(req["model"], "language-model-fixture")
        self.assertEqual(req["max_tool_calls"], 1)
        self.assertFalse(req["parallel_tool_calls"])
        self.assertNotIn("input_fidelity", req["tools"][0])
        self.assertTrue(req["input"][0]["content"][2]["image_url"].endswith(base64.b64encode(png()).decode()))
        with patch.object(gen, "post_once") as post, patch.dict(os.environ, {}, clear=True):
            gen.run(self.task, "language-model-fixture", self.out)
            post.assert_not_called()
        self.assertEqual(manifest["references"][0]["sha256"], gen.digest(png()))

    def test_success_is_not_visual_acceptance_or_size_success(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once", return_value=(response(), "request-fixture")) as post:
            gen.run(self.task, "language-model-fixture", self.out, execute=True)
            with self.assertRaises(ValueError):
                gen.run(self.task, "language-model-fixture", self.out, execute=True)
            self.assertEqual(post.call_count, 1)
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "generated")
        self.assertEqual(manifest["visual_review"], "pending")
        self.assertFalse(manifest["size_matches"])

    def test_timeout_is_unknown_and_never_automatically_retried(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once", side_effect=TimeoutError) as post:
            with self.assertRaises(ValueError):
                gen.run(self.task, "language-model-fixture", self.out, execute=True)
            with self.assertRaises(ValueError):
                gen.run(self.task, "language-model-fixture", self.out, execute=True)
            self.assertEqual(post.call_count, 1)
        self.assertEqual(json.loads((self.out / "manifest.json").read_text())["state"], "unknown")

    def test_changed_reference_cannot_reuse_run(self):
        gen.run(self.task, "language-model-fixture", self.out)
        (self.root / "prompt.txt").write_text("A changed scene.")
        with self.assertRaisesRegex(ValueError, "different inputs"):
            gen.run(self.task, "language-model-fixture", self.out)

    def test_recovery_needs_no_key_or_original_inputs(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once", return_value=(response(), "request-fixture")):
            gen.run(self.task, "language-model-fixture", self.out, execute=True)
        (self.out / "image.png").unlink()
        (self.root / "character.png").unlink()
        with patch.object(gen, "post_once") as post, patch.dict(os.environ, {}, clear=True):
            gen.run(self.task, "language-model-fixture", self.out, recover=True)
            post.assert_not_called()
        self.assertEqual((self.out / "image.png").read_bytes(), png())

    def test_prepared_directory_cannot_claim_a_response(self):
        gen.run(self.task, "language-model-fixture", self.out)
        (self.out / "response.json").write_text(json.dumps(response()))
        with self.assertRaisesRegex(ValueError, "no submitted response"):
            gen.run(self.task, "language-model-fixture", self.out, recover=True)

    def test_copied_response_from_other_task_is_rejected(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once", return_value=(response(), "request-fixture")):
            gen.run(self.task, "language-model-fixture", self.out, execute=True)
        envelope = json.loads((self.out / "response.json").read_text())
        envelope["request_sha256"] = "different-request-fixture"
        (self.out / "response.json").write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, "different request"):
            gen.run(self.task, "language-model-fixture", self.out, recover=True)

    def test_modified_saved_response_is_rejected(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once", return_value=(response(), "request-fixture")):
            gen.run(self.task, "language-model-fixture", self.out, execute=True)
        envelope = json.loads((self.out / "response.json").read_text())
        envelope["response"]["id"] = "another-response"
        (self.out / "response.json").write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            gen.run(self.task, "language-model-fixture", self.out, recover=True)

    def test_partial_multiple_or_wrong_quality_outputs_rejected(self):
        for change in ("partial", "multiple", "quality"):
            item = response()
            if change == "partial": item["status"] = "in_progress"
            elif change == "multiple": item["output"] *= 2
            else: item["output"][0]["quality"] = "low"
            with self.assertRaises(ValueError): gen.extract_result(item)

    def test_bad_png_crc_and_invalid_sizes_rejected(self):
        raw = bytearray(png()); raw[40] ^= 1
        with self.assertRaises(ValueError): gen.png_dimensions(bytes(raw))
        for size in ("auto", "0x1024", "1025x1024", "4096x1024", "3840x512", "16x16"):
            with self.assertRaises(ValueError): gen.parse_size(size)

    def test_auth_error_does_not_echo_server_body_or_secret(self):
        error = urllib.error.HTTPError(gen.ENDPOINT, 401, "private error fixture", {}, None)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret-only"}), patch.object(gen, "post_once", side_effect=error):
            with self.assertRaisesRegex(ValueError, "HTTP 401") as caught:
                gen.run(self.task, "language-model-fixture", self.out, execute=True)
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("test-secret-only", (self.out / "manifest.json").read_text())

    def test_stale_submission_lock_blocks_second_post(self):
        gen.run(self.task, "language-model-fixture", self.out)
        (self.out / "submission.lock").write_text("crashed-before-state-update")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), patch.object(gen, "post_once") as post:
            with self.assertRaises(FileExistsError):
                gen.run(self.task, "language-model-fixture", self.out, execute=True)
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
