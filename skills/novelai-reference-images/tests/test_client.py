import copy
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile
import zlib

SPEC = importlib.util.spec_from_file_location("novelai_image", Path(__file__).resolve().parents[1] / "scripts" / "novelai_image.py")
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


def png(width=64, height=64):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return api.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x7f" * width * 3) * height)) + chunk(b"IEND", b"")


def zipped(name="image_0.png", raw=None, extra=False, symlink=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        item = zipfile.ZipInfo(name)
        if symlink:
            item.create_system = 3
            item.external_attr = 0o120777 << 16
        archive.writestr(item, png() if raw is None else raw)
        if extra:
            archive.writestr("image_1.png", png())
    return stream.getvalue()


def request():
    # This mock fixture does not assert live availability or recommendation.
    return {"model": "nai-diffusion-3", "action": "generate", "input": "one person", "parameters": {"width": 64, "height": 64, "steps": 1, "scale": 5, "n_samples": 1, "sampler": "mock_sampler", "seed": 42, "negative_prompt": "", "image_format": "png"}}


class Response(io.BytesIO):
    def __init__(self, raw, content_type="application/zip", status=201):
        super().__init__(raw)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        if self.error:
            raise self.error
        return self.response


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"

    def test_success_and_no_secret_on_disk(self):
        opener = Opener(Response(zipped()))
        result = api.send(request(), self.run, "test-secret-never-persist", opener)
        self.assertEqual(result["status"], "downloaded_needs_visual_review")
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0].full_url, api.ENDPOINT)
        self.assertEqual(opener.calls[0].get_header("Authorization"), "Bearer test-secret-never-persist")
        for path in self.run.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"test-secret-never-persist", path.read_bytes())
        self.assertEqual(api.recover(self.run)["images"], result["images"])

    def test_timeout_marks_unknown_and_blocks_second_submission(self):
        opener = Opener(error=TimeoutError("private server detail"))
        with self.assertRaises(api.SafeError) as error:
            api.send(request(), self.run, "fake-token", opener)
        self.assertNotIn("private server detail", str(error.exception))
        state = json.loads((self.run / "state.json").read_text())
        self.assertEqual(state["status"], "submission_unknown")
        with self.assertRaises(api.SafeError):
            api.send(request(), self.run, "fake-token", opener)
        self.assertEqual(len(opener.calls), 1)

    def test_http_errors_are_not_retried_or_logged(self):
        for status in (401, 402, 403, 429, 500):
            with self.subTest(status=status):
                error = urllib.error.HTTPError(api.ENDPOINT, status, "private-token", {}, io.BytesIO(b"private prompt"))
                opener = Opener(error=error)
                run = self.root / str(status)
                with self.assertRaises(api.SafeError) as caught:
                    api.send(request(), run, "fake", opener)
                self.assertNotIn("private", str(caught.exception))
                self.assertEqual(len(opener.calls), 1)
                state = (run / "state.json").read_text()
                self.assertNotIn("private", state)
                self.assertEqual(json.loads(state)["http_status"], status)

    def test_wrong_content_type_is_not_an_image(self):
        with self.assertRaises(api.SafeError):
            api.send(request(), self.run, "fake", Opener(Response(b"{}", "application/json")))
        self.assertFalse((self.run / "image-001.png").exists())

    def test_archive_paths_links_and_extra_files_rejected(self):
        for name in ("../outside.png", "/absolute.png", "folder/image.png", "..\\outside.png", "file.txt"):
            with self.subTest(name=name), self.assertRaises(api.SafeError):
                api.unpack(zipped(name), self.root, request())
        for raw in (zipped(extra=True), zipped(symlink=True)):
            with self.assertRaises(api.SafeError):
                api.unpack(raw, self.root, request())
        self.assertFalse((self.root / "image-001.png").exists())

    def test_wrong_image_dimensions_crc_and_truncation(self):
        for raw in (png(128, 64), png()[:-5], b"not png", png()[:-1] + b"X"):
            with self.subTest(length=len(raw)), self.assertRaises(api.SafeError):
                api.unpack(zipped(raw=raw), self.root, request())

    def test_size_limit(self):
        with patch.object(api, "MAX_BYTES", 10), self.assertRaises(api.SafeError):
            api.unpack(zipped(), self.root, request())

    def test_zip_compression_bomb_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("image.png", b"a" * 1000000)
        with self.assertRaises(api.SafeError):
            api.unpack(stream.getvalue(), self.root, request())

    def test_recovery_never_submits(self):
        opener = Opener(Response(zipped(raw=b"damaged")))
        with self.assertRaises(api.SafeError):
            api.send(request(), self.run, "fake", opener)
        self.assertEqual(json.loads((self.run / "state.json").read_text())["status"], "response_saved")
        with patch.object(api.urllib.request, "build_opener", side_effect=AssertionError("network forbidden")):
            with self.assertRaises(api.SafeError):
                api.recover(self.run)

    def test_saved_response_tampering_detected(self):
        api.send(request(), self.run, "fake", Opener(Response(zipped())))
        (self.run / "response" / "response.zip").write_bytes(zipped(raw=png(128, 64)))
        with self.assertRaises(api.SafeError):
            api.recover(self.run)

    def test_prepared_or_http_error_cannot_recover_even_with_response(self):
        api.send(request(), self.run, "fake", Opener(Response(zipped())))
        state = json.loads((self.run / "state.json").read_text())
        for status in ("prepared", "http_error_review_required"):
            with self.subTest(status=status):
                state["status"] = status
                state.pop("response_sha256", None)
                api.save_state(self.run, state)
                with self.assertRaises(api.SafeError):
                    api.recover(self.run)

    def test_unknown_state_loose_zip_has_no_request_binding(self):
        with self.assertRaises(api.SafeError):
            api.send(request(), self.run, "fake", Opener(error=TimeoutError()))
        (self.run / "response.zip").write_bytes(zipped())
        with self.assertRaises(api.SafeError):
            api.recover(self.run)

    def test_response_package_is_bound_to_request_and_submission(self):
        api.send(request(), self.run, "fake", Opener(Response(zipped())))
        receipt_file = self.run / "response" / "receipt.json"
        original = json.loads(receipt_file.read_text())
        for field in ("request_sha256", "correlation_id", "response_sha256"):
            with self.subTest(field=field):
                altered = dict(original, **{field: "another-request"})
                receipt_file.write_text(json.dumps(altered))
                with self.assertRaises(api.SafeError):
                    api.recover(self.run)
        receipt_file.write_text(json.dumps(original))

    def test_other_task_response_package_cannot_be_attached(self):
        other = self.root / "other-task"
        other_body = request()
        other_body["input"] = "a different subject with the same image dimensions"
        api.send(other_body, other, "fake", Opener(Response(zipped())))
        with self.assertRaises(api.SafeError):
            api.send(request(), self.run, "fake", Opener(error=TimeoutError()))
        (other / "response").rename(self.run / "response")
        with self.assertRaises(api.SafeError):
            api.recover(self.run)

    def test_crash_after_atomic_response_before_state_update_can_recover_offline(self):
        original_save = api.save_state
        def crash_on_response_saved(run_dir, state):
            if state["status"] == "response_saved":
                raise OSError("simulated local state write failure")
            original_save(run_dir, state)
        with patch.object(api, "save_state", side_effect=crash_on_response_saved):
            with self.assertRaises(api.SafeError):
                api.send(request(), self.run, "fake", Opener(Response(zipped())))
        state = json.loads((self.run / "state.json").read_text())
        self.assertEqual(state["status"], "submission_unknown")
        self.assertNotIn("response_sha256", state)
        self.assertTrue((self.run / "response" / "receipt.json").is_file())
        with patch.object(api.urllib.request, "build_opener", side_effect=AssertionError("network forbidden")):
            recovered = api.recover(self.run)
        self.assertEqual(recovered["status"], "downloaded_needs_visual_review")

    def test_redirect_refused(self):
        with self.assertRaises(api.SafeError):
            api.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example")

    def test_invalid_configuration_before_network(self):
        edits = [{"n_samples": 2}, {"width": True}, {"seed": -1}, {"scale": float("nan")}, {"image_format": "webp"}, {"director_reference_images": []}]
        for edit in edits:
            body = request()
            body["parameters"].update(edit)
            with self.subTest(edit=edit), self.assertRaises(api.SafeError):
                api.validate(body)
        body = request()
        body["model"] = "REPLACE_VERIFIED_MODEL_ID"
        with self.assertRaises(api.SafeError):
            api.validate(body)

    def test_structured_prompt_mismatch(self):
        body = request()
        body["parameters"]["v4_prompt"] = {"caption": {"base_caption": "different"}}
        with self.assertRaises(api.SafeError):
            api.validate(body)

    def test_img2img_requires_real_image_and_explicit_strength(self):
        body = request()
        body["action"] = "img2img"
        body["parameters"].update(image=api.base64.b64encode(png()).decode(), strength=0.4, noise=0)
        api.validate(body)
        bad = copy.deepcopy(body)
        bad["parameters"]["image"] = "data:image/png;base64," + bad["parameters"]["image"]
        with self.assertRaises(api.SafeError):
            api.validate(bad)
        del body["parameters"]["strength"]
        with self.assertRaises(api.SafeError):
            api.validate(body)

    def test_dry_run_uses_no_network_or_secret(self):
        source = self.root / "request.json"
        source.write_text(json.dumps(request()))
        with patch.object(api.sys, "argv", ["client", "--request", str(source)]), patch.object(api.urllib.request, "build_opener", side_effect=AssertionError("network forbidden")), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(api.main(), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "dry_run_only")


if __name__ == "__main__":
    unittest.main()
