import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('voice_discovery', ROOT / 'scripts/discover.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
IDENTITY = {'character': '莫斯提马', 'series': '明日方舟', 'language': 'zh-CN', 'actor': '若舞', 'aliases': ['Mostima']}
ITEM = {'title': '【明日方舟中文语音】莫斯提马【CV. 若舞】', 'url': 'https://www.bilibili.com/video/BV17a411d7ex',
        'duration': 246.677, 'uploader': 'Example archive uploader'}


class DiscoveryTests(unittest.TestCase):
    def response(self, entries):
        return subprocess.CompletedProcess([], 0, json.dumps({'entries': entries}), '')

    def test_matching_metadata_is_not_official_or_training_approval(self):
        result = m.candidate(ITEM, 'bilibili', IDENTITY)
        self.assertTrue(all(result['metadata_matches'].values()))
        self.assertEqual(result['blockers'], [])
        self.assertFalse(result['ready_for_training'])
        self.assertEqual(result['hosting_authority'], 'unverified')
        self.assertEqual(result['official_recording_status'], 'unverified')
        self.assertEqual(result['training_rights'], 'unknown')

    def test_language_character_and_content_kind_are_distinguished(self):
        cases = [('明日方舟 莫斯提马 日语语音 水树奈奈', 'different_language_in_metadata'),
                 ('明日方舟 莫斯提马 中文模组任务', 'cover_gameplay_or_fandub_title'),
                 ('明日方舟 莫斯提马 中文 AI Cover', 'cover_gameplay_or_fandub_title'),
                 ('明日方舟 爱音 中文语音 若舞', 'character_not_found_in_metadata'),
                 ('明日方舟 莫斯提马 中文/日文语音', 'multiple_languages_require_manual_segmentation')]
        for title, expected in cases:
            with self.subTest(title=title):
                result = m.candidate({**ITEM, 'title': title}, 'bilibili', IDENTITY)
                self.assertIn(expected, result['blockers'])

    def test_alias_missing_language_actor_and_duration_remain_unknown(self):
        item = m.candidate({**ITEM, 'title': 'Mostima voice lines', 'duration': float('nan')}, 'bilibili', IDENTITY)
        self.assertTrue(item['metadata_matches']['character'])
        self.assertFalse(item['metadata_matches']['language'])
        self.assertFalse(item['metadata_matches']['actor'])
        self.assertIsNone(item['duration_seconds'])
        self.assertFalse(item['ready_for_training'])

    def test_url_credentials_media_and_private_hosts_rejected(self):
        for url in ['file:///tmp/voice.wav', 'http://localhost/voice', 'https://user:pass@www.bilibili.com/video/BV17a411d7ex',
                    'https://www.bilibili.com.evil.invalid/video/BV17a411d7ex',
                    'https://www.bilibili.com:443/video/BV17a411d7ex', 'https://cdn.example.invalid/audio.m4a?token=secret']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.canonical_url(url)
        self.assertEqual(m.canonical_url(ITEM['url'] + '?token=private')[1], ITEM['url'] + '/')
        self.assertEqual(m.canonical_url('https://youtu.be/abcdefghijk?t=4')[1], 'https://www.youtube.com/watch?v=abcdefghijk')

    def test_metadata_command_never_downloads_or_inherits_plugins(self):
        def run(command, **kwargs):
            for flag in ('--ignore-config', '--no-plugin-dirs', '--skip-download', '--flat-playlist', '--no-js-runtimes'):
                self.assertIn(flag, command)
            self.assertNotIn('-x', command)
            self.assertNotIn('--cookies-from-browser', command)
            self.assertNotIn('shell', kwargs)
            self.assertTrue(Path(kwargs['cwd']).is_dir())
            self.assertEqual(kwargs['timeout'], 90)
            return self.response([ITEM])
        report = m.discover(IDENTITY, ['bilibili'], run=run)
        self.assertEqual(report['status'], 'candidates_need_review')
        self.assertFalse(report['media_downloaded'])

    def test_failed_provider_does_not_hide_success_from_another(self):
        def run(command, **kwargs):
            if 'bilisearch' in command[-1]:
                return subprocess.CompletedProcess(command, 1, '', '403 Cookie=secret')
            return self.response([{**ITEM, 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}])
        report = m.discover(IDENTITY, ['bilibili', 'youtube'], run=run)
        self.assertEqual(report['status'], 'candidates_need_review')
        self.assertFalse(report['search_complete'])
        self.assertEqual(report['attempts'][0]['error_kind'], 'access_denied')
        self.assertNotIn('Cookie', json.dumps(report))

    def test_missing_timeout_malformed_and_partial_are_not_empty_search(self):
        cases = [FileNotFoundError('tool absent'), subprocess.TimeoutExpired('metadata', 90),
                 subprocess.CompletedProcess([], 0, '<html>error</html>', ''), self.response([None])]
        for case in cases:
            def run(*args, **kwargs):
                if isinstance(case, Exception):
                    raise case
                return case
            with self.subTest(case=type(case).__name__):
                report = m.discover(IDENTITY, ['bilibili'], run=run)
                self.assertEqual(report['status'], 'search_incomplete')
                self.assertFalse(report['search_complete'])

    def test_real_empty_and_blocked_results_are_not_ready(self):
        for rows in [[], [{**ITEM, 'title': '无关角色的玩法攻略'}]]:
            report = m.discover(IDENTITY, ['bilibili'], run=lambda *a, **k: self.response(rows))
            self.assertEqual(report['status'], 'no_matching_candidates')
            self.assertTrue(report['search_complete'])
            self.assertFalse(report['ready_for_training'])

    def test_deduplication_bounds_and_host_mismatch(self):
        rows = [ITEM, {**ITEM, 'url': ITEM['url'] + '?tracking=a'},
                {**ITEM, 'url': 'https://www.youtube.com/watch?v=abcdefghijk'}]
        found, rejected = m.decode_candidates(json.dumps({'entries': rows}), 'bilibili', IDENTITY, 10)
        self.assertEqual(len(found), 1)
        self.assertEqual(rejected, 1)
        self.assertEqual(m.decode_candidates(json.dumps({'entries': rows}), 'bilibili', IDENTITY, 1)[1], 0)

    def test_bilibili_url_only_flat_results_require_inspection_not_rejection(self):
        row = {'_type': 'url', 'url': 'https://www.bilibili.com/video/av259650956', 'ie_key': 'BiliBili', 'id': '259650956'}
        report = m.discover(IDENTITY, ['bilibili'], run=lambda *a, **k: self.response([row]))
        self.assertEqual(report['status'], 'candidates_need_review')
        self.assertTrue(report['search_complete'])
        self.assertTrue(report['candidates'][0]['needs_details'])
        self.assertEqual(report['candidates'][0]['title'], '')
        self.assertEqual(report['candidates'][0]['blockers'], [])
        self.assertFalse(report['ready_for_training'])

    def test_full_metadata_inspection_is_still_no_download(self):
        command = m.search_command('yt-dlp', 'bilibili', '', 8, ITEM['url'])
        self.assertIn('--no-playlist', command)
        self.assertNotIn('--flat-playlist', command)
        self.assertIn('--skip-download', command)
        found, rejected = m.decode_candidates(json.dumps(ITEM), 'bilibili', IDENTITY, 8)
        self.assertEqual(len(found), 1)
        self.assertEqual(rejected, 0)

    def test_bilibili_parts_keep_distinct_language_recordings(self):
        base = ITEM['url'] + '/'
        page = m.canonical_url(base + '?p=2&tracking=remove')[1]
        self.assertEqual(page, base + '?p=2')
        self.assertEqual(m.search_command('yt-dlp', 'bilibili', '', 8, page)[-1], page)
        rows = [{**ITEM, 'title': '明日方舟 莫斯提马 日文语音', 'url': base + '?p=1'},
                {**ITEM, 'url': base + '?p=2'}]
        report = m.discover(IDENTITY, ['bilibili'], run=lambda *a, **k: self.response(rows))
        self.assertEqual(len(report['candidates']), 2)
        self.assertEqual(report['status'], 'candidates_need_review')
        self.assertEqual(report['candidates'][0]['url'], base + '?p=2')
        for invalid in ('p=0', 'p=-1', 'p=2&p=3', 'p=', 'p=1.5'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                m.canonical_url(base + '?' + invalid)

    def test_output_collision_stops_before_any_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'report.json'
            output.write_text('existing')
            with patch.object(m, 'discover') as called:
                code = m.main(['--character', '莫斯提马', '--series', '明日方舟', '--language', 'zh-CN', '--output', str(output)])
            self.assertEqual(code, 2)
            called.assert_not_called()
            self.assertEqual(output.read_text(), 'existing')

    def test_invalid_limits_and_control_characters_do_not_search(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m, 'discover') as called:
            for extra in [['--limit', '999'], ['--timeout', '0'], ['--alias', 'bad\ninput']]:
                code = m.main(['--character', '莫斯提马', '--series', '明日方舟', '--language', 'zh-CN',
                               '--output', str(Path(tmp) / 'new.json'), *extra])
                self.assertEqual(code, 2)
            called.assert_not_called()

    def test_real_cli_missing_tool_saves_failure_report_without_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/discover.py'), '--character', '莫斯提马',
                                     '--series', '明日方舟', '--language', 'zh-CN', '--yt-dlp', str(root / 'absent'),
                                     '--output', str(root / 'report.json')], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            report = json.loads((root / 'report.json').read_text())
            self.assertEqual(report['attempts'][0]['status'], 'tool_missing')
            self.assertEqual({p.name for p in root.iterdir()}, {'report.json'})

    @unittest.skipIf(sys.platform == 'win32', 'POSIX executable fixture; core path resolution is portable')
    def test_relative_executable_survives_temporary_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = root / 'metadata-fixture'
            tool.write_text('#!' + sys.executable + '\nimport json\nprint(' + repr(json.dumps({'entries': [ITEM]})) + ')\n')
            tool.chmod(0o755)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/discover.py'), '--character', '莫斯提马',
                                     '--series', '明日方舟', '--language', 'zh-CN', '--yt-dlp', './metadata-fixture',
                                     '--output', 'report.json'], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'report.json').read_text())
            self.assertEqual(report['status'], 'candidates_need_review')
            self.assertEqual(report['candidates'][0]['url'], ITEM['url'] + '/')


if __name__ == '__main__':
    unittest.main()
