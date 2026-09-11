import argparse
from contextlib import contextmanager
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location("run_shot", Path(__file__).parents[1] / "scripts" / "run_shot.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

GRAPH = {
    "1": {"class_type": "MakeVideo", "inputs": {"model": "h3.safetensors", "frames": 24}},
    "92": {"class_type": "SaveVideo", "inputs": {"video": ["1", 0], "format": "mp4"}},
}
INFO = {
    "MakeVideo": {"input": {"required": {"model": [["h3.safetensors"]], "frames": ["INT", {"min": 1}]}}, "output": ["VIDEO"]},
    "SaveVideo": {"input": {"required": {"video": ["VIDEO"], "format": [["mp4"]]}}, "output": []},
}
RECORD = {"filename": "clip_00001_.mp4", "subfolder": "video", "type": "output"}


def success(outputs=None):
    return {"status": {"completed": True, "status_str": "success"},
            "outputs": {"92": {"images": [RECORD], "animated": [True]}} if outputs is None else outputs}


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Type": "video/mp4", "Content-Length": str(len(data))}


class FakeClient:
    endpoint_sha256 = "endpoint-a"

    def __init__(self):
        self.calls = []
        self.replies = {"/object_info": INFO, "/history/task-id": {"task-id": success()},
                        "/queue": {"queue_running": [], "queue_pending": []}, "/history?max_items=1000": {}}
        self.submission_error = None
        self.payload = None
        self.identity_value = "environment-a"
        self.download_bytes = b"fake video"

    def remaining(self):
        return 10

    def identity(self):
        return self.identity_value

    def json(self, path, data=None):
        self.calls.append((path, data))
        if path == "/prompt":
            self.payload = data
            if self.submission_error:
                raise self.submission_error
            return {"prompt_id": "task-id"}
        reply = self.replies[path]
        if isinstance(reply, Exception):
            raise reply
        return reply

    def open(self, path, data=None, headers=None):
        self.calls.append((path, data))
        return FakeResponse(self.download_bytes)


class RunShotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.graph_path = self.base / "api.json"
        self.graph_path.write_text(json.dumps(GRAPH))
        self.run_dir = self.base / "run"
        self.client = FakeClient()

    def tearDown(self):
        self.temp.cleanup()

    def args(self, action="execute", **kwargs):
        value = dict(run_dir=str(self.run_dir), workflow=str(self.graph_path), frames=24, fps=24,
                     width=1344, height=768, output_node=None, max_download_mib=2,
                     check=action == "check", execute=action == "execute", resume=action == "resume")
        value.update(kwargs)
        return argparse.Namespace(**value)

    def state(self):
        return json.loads((self.run_dir / "state.json").read_text())

    def post_count(self):
        return sum(path == "/prompt" for path, _ in self.client.calls)

    def test_check_is_read_only_and_can_upgrade_same_directory(self):
        state = runner.run(self.args("check"), self.client)
        self.assertEqual(state["phase"], "checked")
        self.assertTrue(state["preflight"]["read_only"])
        self.assertEqual(self.post_count(), 0)
        with patch.object(runner, "verify_media", return_value={"full_decode": "passed"}):
            runner.run(self.args(), self.client)
        self.assertEqual(self.post_count(), 1)

    def test_success_requires_media_and_never_posts_twice(self):
        with patch.object(runner, "verify_media", return_value={"full_decode": "passed"}):
            state = runner.run(self.args(), self.client)
        self.assertEqual(state["phase"], "media_verified")
        self.assertEqual(state["visual_review"], "pending")
        self.assertEqual(state["audio_review"], "pending")
        with self.assertRaisesRegex(runner.ShotError, "already attempted"):
            runner.run(self.args(), self.client)
        runner.run(self.args("resume", workflow=None, frames=None, fps=None, width=None, height=None), self.client)
        self.assertEqual(self.post_count(), 1)

    def test_resume_checked_never_submits(self):
        runner.run(self.args("check"), self.client)
        runner.run(self.args("resume"), self.client)
        self.assertEqual(self.post_count(), 0)

    def test_cross_endpoint_resume_refused_before_network(self):
        runner.run(self.args("check"), self.client)
        self.client.endpoint_sha256 = "different-endpoint"
        calls = len(self.client.calls)
        with self.assertRaisesRegex(runner.ShotError, "different ComfyUI endpoint"):
            runner.run(self.args("resume"), self.client)
        self.assertEqual(len(self.client.calls), calls)

    def test_changed_environment_resume_refused(self):
        runner.run(self.args("check"), self.client)
        self.client.identity_value = "other-machine"
        with self.assertRaisesRegex(runner.ShotError, "fingerprint changed"):
            runner.run(self.args("resume"), self.client)

    def test_false_success_without_requested_video_refused(self):
        self.client.replies["/history/task-id"] = {"task-id": success({"91": {"images": [RECORD]}})}
        with self.assertRaisesRegex(runner.ShotError, "lacks exactly one video"):
            runner.run(self.args(), self.client)
        self.assertFalse(list(self.run_dir.glob("video.*")))
        self.assertEqual(self.post_count(), 1)

    def test_wrong_ui_key_is_not_guessed(self):
        with self.assertRaises(runner.ShotError):
            runner.output_record(success({"92": {"videos": [RECORD]}}), "92")

    def test_execution_error_is_not_success(self):
        with self.assertRaisesRegex(runner.ShotError, "execution failed"):
            runner.output_record({"status": {"completed": True, "status_str": "error"}}, "92")

    def test_history_from_other_workflow_is_not_accepted(self):
        self.client.replies["/history/task-id"] = {"task-id": {**success(), "prompt": [0, "task-id", GRAPH, {"client_id": "other"}]}}
        with self.assertRaisesRegex(runner.ShotError, "different client or workflow"):
            runner.run(self.args(), self.client)

    def test_h3_dimensions_and_frames_checked_before_submit(self):
        graph = {"1": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {"width": 768, "height": 448, "length": 243}}}
        expected = {"width": 768, "height": 448, "frames": 243, "fps": 24}
        runner.check_expected(graph, expected)
        for key in ("width", "height", "frames"):
            with self.assertRaisesRegex(runner.ShotError, "differ from the expected"):
                runner.check_expected(graph, {**expected, key: expected[key] + 1})

    def test_connection_loss_recovers_original_from_queue(self):
        self.client.submission_error = runner.Pending("Connection interrupted")
        with self.assertRaises(runner.Pending):
            runner.run(self.args(), self.client)
        self.assertEqual(self.state()["phase"], "submission_unknown")
        self.client.replies["/queue"] = {"queue_pending": [[0, "task-id", GRAPH,
                                                          {"client_id": self.state()["client_id"]}, ["92"]]]}
        with patch.object(runner, "verify_media", return_value={}):
            state = runner.run(self.args("resume"), self.client)
        self.assertEqual(state["prompt_id"], "task-id")
        self.assertEqual(self.post_count(), 1)

    def test_connection_loss_recovers_original_from_history(self):
        self.client.submission_error = runner.Pending("Connection interrupted")
        with self.assertRaises(runner.Pending):
            runner.run(self.args(), self.client)
        original = [0, "task-id", GRAPH, {"client_id": self.state()["client_id"]}, ["92"]]
        self.client.replies["/history?max_items=1000"] = {"task-id": {"prompt": original, **success()}}
        with patch.object(runner, "verify_media", return_value={}):
            runner.run(self.args("resume"), self.client)
        self.assertEqual(self.post_count(), 1)

    def test_unknown_submission_stays_pending_without_resubmit(self):
        self.client.submission_error = runner.Pending("Connection interrupted")
        with self.assertRaises(runner.Pending):
            runner.run(self.args(), self.client)
        for _ in range(2):
            with self.assertRaisesRegex(runner.Pending, "absent from queue"):
                runner.run(self.args("resume"), self.client)
        self.assertEqual(self.post_count(), 1)

    def test_missing_model_prevents_submit(self):
        info = json.loads(json.dumps(INFO))
        info["MakeVideo"]["input"]["required"]["model"][0] = []
        self.client.replies["/object_info"] = info
        with self.assertRaisesRegex(runner.ShotError, "Unavailable selection"):
            runner.run(self.args(), self.client)
        self.assertEqual(self.post_count(), 0)

    def test_changed_workflow_or_expectation_refuses_directory_reuse(self):
        runner.run(self.args("check"), self.client)
        with self.assertRaisesRegex(runner.ShotError, "parameters differ"):
            runner.run(self.args("resume", frames=25), self.client)
        saved_graph = self.run_dir / "workflow.api.json"
        saved_graph.write_text(json.dumps({**GRAPH, "other": {}}))
        with self.assertRaisesRegex(runner.ShotError, "fingerprint changed"):
            runner.run(self.args("resume"), self.client)

    def test_remote_filename_never_becomes_a_local_path(self):
        record = {**RECORD, "filename": "../../outside.mp4", "subfolder": "../remote"}
        self.client.replies["/history/task-id"] = {"task-id": success({"92": {"images": [record]}})}
        with patch.object(runner, "verify_media", return_value={}):
            runner.run(self.args(), self.client)
        self.assertTrue((self.run_dir / "video.mp4").is_file())
        self.assertFalse((self.base / "outside.mp4").exists())
        view = [path for path, _ in self.client.calls if path.startswith("/view?")][0]
        self.assertIn("filename=..%2F..%2Foutside.mp4", view)

    def test_bad_content_type_and_short_download_are_not_published(self):
        target = self.base / "video.mp4"
        with patch.object(self.client, "open", return_value=FakeResponse(b"login", {"Content-Type": "text/html"})):
            with self.assertRaisesRegex(runner.ShotError, "non-video"):
                runner.download(self.client, RECORD, target, 100)
        with patch.object(self.client, "open", return_value=FakeResponse(b"short", {"Content-Type": "video/mp4", "Content-Length": "20"})):
            with self.assertRaises(runner.Pending):
                runner.download(self.client, RECORD, target, 100)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix(".download").exists())

    def test_download_limit_enforced_without_content_length(self):
        with patch.object(self.client, "open", return_value=FakeResponse(b"large payload", {"Content-Type": "video/mp4"})):
            with self.assertRaisesRegex(runner.ShotError, "size limit"):
                runner.download(self.client, RECORD, self.base / "video.mp4", 3)

    def test_downloaded_media_resume_does_not_generate_or_download_again(self):
        with patch.object(runner, "verify_media", side_effect=runner.Pending("inspection timeout")):
            with self.assertRaises(runner.Pending):
                runner.run(self.args(), self.client)
        self.assertEqual(self.state()["phase"], "downloaded")
        downloads = sum(path.startswith("/view?") for path, _ in self.client.calls)
        with patch.object(runner, "verify_media", return_value={}):
            runner.run(self.args("resume"), self.client)
        self.assertEqual(self.post_count(), 1)
        self.assertEqual(sum(path.startswith("/view?") for path, _ in self.client.calls), downloads)


class TransportAndMediaTests(unittest.TestCase):
    def test_url_rejects_embedded_secrets(self):
        for url in ("https://user:secret@example.test", "https://example.test?key=secret", "file:///private"):
            with self.assertRaises(runner.ShotError) as caught:
                runner.Client(url)
            self.assertNotIn("secret", str(caught.exception))

    def test_auth_requires_https_for_remote(self):
        with self.assertRaisesRegex(runner.ShotError, "requires HTTPS"):
            runner.Client("http://example.test:8188", token="secret")

    def test_redirect_is_refused(self):
        with self.assertRaisesRegex(runner.ShotError, "redirect refused"):
            runner.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test")

    def test_http_request_is_bound_to_configured_origin(self):
        client = runner.Client("https://example.test/comfy", token="secret")
        with patch.object(client.opener, "open", return_value=FakeResponse(b"{}")) as opened:
            client.json("/queue")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test:443/comfy/queue")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        with self.assertRaises(runner.ShotError):
            client.open("//other.test/path")

    def probe(self, frames=24, audio=True):
        streams = [{"index": 0, "codec_type": "video", "width": 1344, "height": 768,
                    "sample_aspect_ratio": "1:1", "start_time": "0.0",
                    "nb_read_frames": str(frames), "avg_frame_rate": "24/1"}]
        if audio:
            streams.append({"index": 1, "codec_type": "audio", "nb_read_frames": "48"})
        return subprocess.CompletedProcess([], 0, json.dumps({"streams": streams}).encode(), b"")

    def packets(self, start=0.0, duration=1.0):
        packets = [{"stream_index": 1, "pts_time": str(start), "duration_time": str(duration)}]
        return subprocess.CompletedProcess([], 0, json.dumps({"packets": packets}).encode(), b"")

    def test_media_wrong_frames_and_missing_audio_fail(self):
        expected = {"frames": 24, "width": 1344, "height": 768, "fps": 24}
        for result in (self.probe(frames=23), self.probe(audio=False)):
            with patch.object(runner.subprocess, "run", return_value=result):
                with self.assertRaises(runner.ShotError):
                    runner.verify_media(Path("video.mp4"), expected, FakeClient())

    def test_complete_decode_failure_is_rejected(self):
        with patch.object(runner.subprocess, "run", side_effect=[self.probe(), self.packets(), subprocess.CompletedProcess([], 1, b"", b"secret-path")]):
            with self.assertRaisesRegex(runner.ShotError, "decoding failed") as caught:
                runner.verify_media(Path("video.mp4"), {"frames": 24, "width": 1344, "height": 768, "fps": 24}, FakeClient())
        self.assertNotIn("secret-path", str(caught.exception))

    def test_valid_media_requires_human_review(self):
        with patch.object(runner.subprocess, "run", side_effect=[self.probe(), self.packets(), subprocess.CompletedProcess([], 0, b"", b"")]):
            result = runner.verify_media(Path("video.mp4"), {"frames": 24, "width": 1344, "height": 768, "fps": 24}, FakeClient())
        self.assertEqual(result["full_decode"], "passed")
        self.assertEqual(result["visual_review"], "pending")
        self.assertEqual(result["audio_review"], "pending")
        self.assertEqual(result["audio_timing"][0]["duration_seconds"], 1.0)

    def test_short_or_late_audio_fails_even_if_decodable(self):
        for packets in (self.packets(duration=0.1), self.packets(start=0.3, duration=0.7), self.packets(duration=2)):
            with patch.object(runner.subprocess, "run", side_effect=[self.probe(), packets]):
                with self.assertRaisesRegex(runner.ShotError, "audio start/end"):
                    runner.verify_media(Path("video.mp4"), {"frames": 24, "width": 1344, "height": 768, "fps": 24}, FakeClient())

    def test_normal_aac_delay_is_accepted_with_semantics_still_pending(self):
        with patch.object(runner.subprocess, "run", side_effect=[self.probe(), self.packets(start=-0.021333, duration=1.024), subprocess.CompletedProcess([], 0, b"", b"")]):
            result = runner.verify_media(Path("video.mp4"), {"frames": 24, "width": 1344, "height": 768, "fps": 24}, FakeClient())
        self.assertEqual(result["audio_timing_check"], "passed")
        self.assertEqual(result["audio_review"], "pending")

    def test_non_square_pixels_fail(self):
        probe = self.probe()
        payload = json.loads(probe.stdout)
        payload["streams"][0]["sample_aspect_ratio"] = "4:3"
        probe.stdout = json.dumps(payload).encode()
        with patch.object(runner.subprocess, "run", return_value=probe):
            with self.assertRaisesRegex(runner.ShotError, "aspect ratio must be 1:1"):
                runner.verify_media(Path("video.mp4"), {"frames": 24, "width": 1344, "height": 768, "fps": 24}, FakeClient())


class AutogrowAndLockTests(unittest.TestCase):
    def fixture(self):
        # Shape emitted by official H3 Autogrow.Input.as_dict / TemplatePrefix.as_dict.
        image = ["COMFY_AUTOGROW_V3", {"template": {
            "input": {"required": {"ref_image": ["IMAGE", {"tooltip": "Reference image"}]}},
            "prefix": "ref_image_", "min": 0, "max": 9}}]
        audio = ["COMFY_AUTOGROW_V3", {"template": {
            "input": {"required": {"ref_audio": ["AUDIO", {"tooltip": "Standalone reference audio"}]}},
            "prefix": "ref_audio_", "min": 0, "max": 3}}]
        info = {
            "MiniMaxH3ReferenceToVideo": {"input": {"optional": {"ref_images": image, "ref_audios": audio}},
                                         "output": ["CONDITIONING", "LATENT"]},
            "ImageFixture": {"input": {"required": {}}, "output": ["IMAGE"]},
            "AudioFixture": {"input": {"required": {}}, "output": ["AUDIO"]},
        }
        graph = {
            "1": {"class_type": "ImageFixture", "inputs": {}},
            "2": {"class_type": "AudioFixture", "inputs": {}},
            "136": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
                "ref_images.ref_image_0": ["1", 0], "ref_audios.ref_audio_0": ["2", 0]}},
        }
        client = FakeClient()
        client.replies["/object_info"] = info
        return client, graph, info

    def test_real_h3_autogrow_schema_accepts_image_and_audio_slots(self):
        client, graph, _ = self.fixture()
        self.assertTrue(runner.preflight(client, graph)["read_only"])

    def test_autogrow_unknown_and_out_of_range_slots_are_rejected(self):
        for key in ("ref_images.ref_image_9", "ref_audios.ref_audio_3", "ref_images.wrong_0", "unknown.ref_image_0"):
            client, graph, _ = self.fixture()
            graph["136"]["inputs"][key] = ["1", 0]
            with self.assertRaisesRegex(runner.ShotError, "Unknown node input"):
                runner.preflight(client, graph)

    def test_autogrow_wrong_socket_type_is_rejected(self):
        client, graph, _ = self.fixture()
        graph["136"]["inputs"]["ref_images.ref_image_0"] = ["2", 0]
        with self.assertRaisesRegex(runner.ShotError, "output type does not match"):
            runner.preflight(client, graph)

    def test_autogrow_required_slots_and_name_templates(self):
        declared = {"required": {"items": ["COMFY_AUTOGROW_V3", {"template": {
            "input": {"required": {"image": ["IMAGE"]}}, "names": ["left", "right"], "min": 1}}]}}
        self.assertEqual(runner.expanded_inputs(declared), {
            "required": {"items.left": ["IMAGE"]}, "optional": {"items.right": ["IMAGE"]}})

    def test_windows_lock_and_unlock_use_same_byte(self):
        fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=Mock())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(runner.os, "name", "nt"), patch.dict(runner.sys.modules, {"msvcrt": fake}):
                with runner.run_lock(directory):
                    self.assertEqual(fake.locking.call_args.args[1:], (2, 1))
            self.assertEqual(fake.locking.call_args.args[1:], (0, 1))
            self.assertEqual((directory / ".lock").read_bytes(), b"\0")

    def test_windows_competing_process_lock_refuses_entry(self):
        fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=Mock(side_effect=OSError()))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(runner.os, "name", "nt"), patch.dict(runner.sys.modules, {"msvcrt": fake}):
                with self.assertRaisesRegex(runner.ShotError, "Another process"):
                    with runner.run_lock(directory):
                        self.fail("must not enter")


if __name__ == "__main__":
    unittest.main()
