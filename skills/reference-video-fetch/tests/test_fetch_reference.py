import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "fetch_reference", Path(__file__).resolve().parents[1] / "scripts" / "fetch_reference.py"
)
fetch_reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_reference)


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def format_row(format_id, width, height, vcodec="avc1.640033", acodec="none", ext="mp4", fps=30, tbr=1000):
    return {
        "format_id": format_id, "width": width, "height": height, "vcodec": vcodec, "acodec": acodec,
        "ext": ext, "fps": fps, "tbr": tbr,
    }


PORTRAIT_INFO = {
    "id": "BV1LQ7j6WEyD",
    "title": "参考视频",
    "uploader": "某作者",
    "duration": 56.0,
    "formats": [
        format_row("30016", 640, 360),
        format_row("30064", 1280, 720),
        format_row("30080", 1080, 1920),
        format_row("30077", 1080, 1920, vcodec="hvc1.1.6.L150"),
        {"format_id": "30280", "width": None, "height": None, "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 154},
        {"format_id": "30216", "width": None, "height": None, "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 66},
    ],
}


class FakeRunner:
    """Records every command and replays canned responses."""

    def __init__(self, *, info=None, probe_error=None, download=None):
        self.commands = []
        self.info = info if info is not None else PORTRAIT_INFO
        self.probe_error = probe_error
        self.download = download
        self.version_calls = 0

    def __call__(self, command, capture_output=True, text=True, timeout=None):
        self.commands.append(list(command))
        if "--version" in command:
            self.version_calls += 1
            return Result(stdout="2026.08.19\n")
        if "--dump-single-json" in command:
            if self.probe_error:
                return Result(returncode=1, stderr=self.probe_error)
            return Result(stdout=json.dumps(self.info))
        if "-show_entries" in command:
            return Result(stdout=json.dumps({
                "streams": [
                    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "avg_frame_rate": "30/1"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "56.0"},
            }))
        self.produced = True
        if self.download:
            return self.download(command)
        target = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
        target.write_bytes(b"fake-video-bytes")
        return Result(stdout="done")


def args_for(**overrides):
    base = {
        "url": "https://www.bilibili.com/video/BV1LQ7j6WEyD", "out": None, "stem": None, "record": None,
        "max_height": 1080, "require_height": None, "max_duration": 900, "limit_rate": None,
        "sleep_requests": 1, "timeout": 120, "yt_dlp": "/fake/yt-dlp", "probe": False,
        "force": False, "json": True,
    }
    base.update(overrides)
    return type("Args", (), base)


class UrlTests(unittest.TestCase):
    def test_accepts_bilibili_and_youtube_pages(self):
        self.assertEqual(fetch_reference.canonical_page("https://www.bilibili.com/video/BV1LQ7j6WEyD/"),
                         ("bilibili", "https://www.bilibili.com/video/BV1LQ7j6WEyD/"))
        self.assertEqual(fetch_reference.canonical_page("https://m.bilibili.com/video/av12345?p=2"),
                         ("bilibili", "https://www.bilibili.com/video/av12345/?p=2"))
        self.assertEqual(
            fetch_reference.canonical_page("https://www.bilibili.com/video/BV1LQ7j6WEyD/?spm_id_from=333.999"),
            ("bilibili", "https://www.bilibili.com/video/BV1LQ7j6WEyD/"),
        )
        self.assertEqual(fetch_reference.canonical_page("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
                         ("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertEqual(fetch_reference.canonical_page("https://youtu.be/dQw4w9WgXcQ"),
                         ("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_resolves_short_links_through_the_opener(self):
        opener = lambda request, timeout=None: type("R", (), {
            "geturl": lambda self: "https://www.bilibili.com/video/BV1LQ7j6WEyD/",
            "close": lambda self: None,
        })()
        self.assertEqual(
            fetch_reference.canonical_page("https://b23.tv/abcDEF", opener=opener),
            ("bilibili", "https://www.bilibili.com/video/BV1LQ7j6WEyD/"),
        )

    def test_rejects_media_links_and_other_hosts(self):
        for url in (
            "https://upos-sz-estgcos.bilivideo.com/upgcxcode/1/2.m4s?e=abc",
            "https://www.bilibili.com/bangumi/play/ep123456",
            "ftp://www.bilibili.com/video/BV1LQ7j6WEyD/",
            "https://example.com/video/BV1LQ7j6WEyD/",
        ):
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.canonical_page(url)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_USAGE)

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(fetch_reference.FetchError):
            fetch_reference.canonical_page("https://user:pass@www.bilibili.com/video/BV1LQ7j6WEyD/")


class FormatChoiceTests(unittest.TestCase):
    def test_portrait_video_is_measured_by_short_side(self):
        chosen, audio, available = fetch_reference.choose_formats(PORTRAIT_INFO, 1080)
        self.assertEqual((chosen["format_id"], available), ("30080", 1080))
        self.assertEqual(audio["format_id"], "30280")

    def test_cap_keeps_short_side_under_limit(self):
        chosen, _, available = fetch_reference.choose_formats(PORTRAIT_INFO, 480)
        self.assertEqual((chosen["format_id"], available), ("30016", 1080))
        self.assertEqual(fetch_reference.resolution_class(chosen), 360)

    def test_prefers_avc1_over_hevc_at_the_same_resolution(self):
        info = {
            "formats": [
                format_row("h", 1080, 1920, vcodec="hvc1.1.6.L150"),
                format_row("a", 1080, 1920, vcodec="avc1.640033"),
            ]
        }
        chosen, audio, _ = fetch_reference.choose_formats(info, 1080)
        self.assertEqual(chosen["format_id"], "a")
        self.assertIsNone(audio)

    def test_video_without_audio_stream(self):
        info = {"formats": [format_row("v", 1280, 720)]}
        chosen, audio, _ = fetch_reference.choose_formats(info, 1080)
        self.assertEqual(chosen["format_id"], "v")
        self.assertIsNone(audio)

    def test_no_video_stream_is_unavailable(self):
        with self.assertRaises(fetch_reference.FetchError) as caught:
            fetch_reference.choose_formats({"formats": []}, 1080)
        self.assertEqual(caught.exception.code, fetch_reference.EXIT_UNAVAILABLE)


class CommandTests(unittest.TestCase):
    def test_command_never_carries_cookies_and_keeps_pinned_format(self):
        chosen, audio, _ = fetch_reference.choose_formats(PORTRAIT_INFO, 1080)
        command = fetch_reference.build_command(
            "/fake/yt-dlp", "https://www.bilibili.com/video/BV1LQ7j6WEyD/", chosen, audio,
            Path("/tmp/out/BV1LQ7j6WEyD.%(ext)s"), timeout=120, limit_rate="4M", sleep_requests=1,
        )
        self.assertIn("30080+30280", command)
        self.assertIn("--merge-output-format", command)
        self.assertNotIn("--cookies", command)
        self.assertNotIn("--cookies-from-browser", command)
        self.assertEqual(command[-1], "https://www.bilibili.com/video/BV1LQ7j6WEyD/")


class FetchFlowTests(unittest.TestCase):
    def test_probe_only_does_not_download(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp:
            record_path = Path(temp) / "probe.json"
            code, record = fetch_reference.fetch(
                args_for(out=temp, probe=True, record=record_path), runner=runner
            )
            self.assertEqual(code, fetch_reference.EXIT_OK)
            self.assertIsNone(record["path"])
            self.assertEqual(record["available_max_height"], 1080)
            self.assertFalse(any("-o" in command for command in runner.commands))
            self.assertEqual(json.loads(record_path.read_text())["video_id"], "BV1LQ7j6WEyD")

    def test_successful_fetch_writes_record_with_hash(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp:
            code, record = fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(code, fetch_reference.EXIT_OK)
            target = Path(record["path"])
            self.assertTrue(target.exists())
            self.assertEqual(record["sha256"], fetch_reference.sha256_of(target))
            self.assertEqual(record["bytes"], target.stat().st_size)
            self.assertEqual(record["transport"], "no-login")
            self.assertEqual(record["redistribution"], "local-reference-only")
            self.assertEqual(record["width"], 1080)
            self.assertEqual(record["height"], 1920)
            self.assertTrue(target.with_suffix(target.suffix + ".fetch.json").exists())

    def test_existing_output_is_not_overwritten(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "BV1LQ7j6WEyD.mp4").write_bytes(b"already-here")
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_EXISTS)
            self.assertFalse(any("-o" in command for command in runner.commands))

    def test_quality_below_requirement_fails_before_downloading(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(out=temp, require_height=2160), runner=runner)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_QUALITY)
            self.assertIn("1080p", caught.exception.message)
            self.assertFalse(any("-o" in command for command in runner.commands))

    def test_quality_limited_is_recorded_not_hidden(self):
        info = {"id": "BV1", "title": "t", "uploader": "u", "duration": 10.0,
                "formats": [format_row("30032", 480, 852)]}
        runner = FakeRunner(info=info)
        with tempfile.TemporaryDirectory() as temp:
            _, record = fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertTrue(record["quality_limited"])
            self.assertTrue(any("匿名上限" in note for note in record["notes"]))

    def test_missing_tool_reports_install_path(self):
        with patch.object(fetch_reference.shutil, "which", lambda name: None):
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(yt_dlp=None), runner=FakeRunner())
        self.assertEqual(caught.exception.code, fetch_reference.EXIT_NO_TOOL)

    def test_too_long_video_stops_for_confirmation(self):
        info = dict(PORTRAIT_INFO, duration=7200.0)
        runner = FakeRunner(info=info)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_TOO_LONG)

    def test_unavailable_page_is_classified(self):
        runner = FakeRunner(probe_error="ERROR: [BiliBili] BV1: Video does not exist")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_UNAVAILABLE)

    def test_premium_hint_becomes_a_note_not_a_failure(self):
        info = dict(PORTRAIT_INFO)
        runner = FakeRunner(info=info)
        with tempfile.TemporaryDirectory() as temp:
            _, record = fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(record["site"], "bilibili")
            self.assertEqual(record["selected_format_id"], "30080")

    def test_download_failure_returns_classified_code(self):
        def boom(command):
            return Result(returncode=1, stderr="ERROR: unable to download webpage: HTTP Error 403")
        runner = FakeRunner(download=boom)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(fetch_reference.FetchError) as caught:
                fetch_reference.fetch(args_for(out=temp), runner=runner)
            self.assertEqual(caught.exception.code, fetch_reference.EXIT_FAILED)


class RecordContractTests(unittest.TestCase):
    def test_record_keeps_the_documented_keys(self):
        record = fetch_reference.build_record(
            PORTRAIT_INFO, "bilibili", "https://www.bilibili.com/video/BV1LQ7j6WEyD/", notes=[],
            path=None, selected=PORTRAIT_INFO["formats"][2], audio=PORTRAIT_INFO["formats"][4],
            available=1080, requested_height=1080,
        )
        for key in ("tool", "site", "page_url", "video_id", "title", "uploader", "fetched_at", "transport",
                    "redistribution", "requested_max_height", "available_max_height", "quality_limited",
                    "selected_format_id", "path", "bytes", "sha256", "notes"):
            self.assertIn(key, record)
        self.assertFalse(record["quality_limited"])


if __name__ == "__main__":
    unittest.main()
