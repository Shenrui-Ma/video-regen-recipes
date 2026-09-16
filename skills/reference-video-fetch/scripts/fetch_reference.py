#!/usr/bin/env python3
"""Fetch a public reference video page with yt-dlp, without any login.

Only public page URLs are accepted (Bilibili video pages, YouTube watch pages).
Signed CDN links are rejected: they expire, they skip the source record, and
they come from a page the template should point at instead. No cookies, no
account state and no browser profile are ever passed to yt-dlp, so the quality
ceiling is whatever the site serves anonymously.

The bytes stay on the user's machine. This exists so a third-party reference
does not have to be redistributed through this repository or the media library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_TOOL = 3
EXIT_UNAVAILABLE = 4
EXIT_QUALITY = 5
EXIT_EXISTS = 6
EXIT_TOO_LONG = 7
EXIT_FAILED = 8

SCHEMA_VERSION = 1
DEFAULT_MAX_HEIGHT = 0  # 0 = no cap: take the best quality the site serves anonymously
DEFAULT_MAX_DURATION = 900

BILIBILI_HOSTS = {'www.bilibili.com', 'bilibili.com', 'm.bilibili.com'}
SHORT_HOSTS = {'b23.tv', 'www.b23.tv'}
YOUTUBE_HOSTS = {'www.youtube.com', 'youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be'}
MEDIA_HOST_MARKERS = ('bilivideo.com', 'akamaized.net', 'hdslb.com')

VIDEO_CODEC_PREFERENCE = ('avc1', 'h264')


class FetchError(Exception):
    """A classified failure the caller can turn into an exit code."""

    def __init__(self, code, message, *, notes=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.notes = list(notes or [])


def canonical_page(value, *, opener=None):
    """Return (site, page_url) for a supported public page URL."""
    if not isinstance(value, str) or not value.strip():
        raise FetchError(EXIT_USAGE, '需要一个公开的视频页面链接')
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in ('http', 'https'):
        raise FetchError(EXIT_USAGE, '只接受 http(s) 的公开页面链接')
    if parsed.username or parsed.password:
        raise FetchError(EXIT_USAGE, '链接里不允许携带账号信息')
    host = (parsed.hostname or '').lower()
    if host in SHORT_HOSTS:
        resolved = resolve_short(value.strip(), opener=opener)
        return canonical_page(resolved, opener=opener)
    if host in MEDIA_HOST_MARKERS or any(marker in host for marker in MEDIA_HOST_MARKERS):
        raise FetchError(EXIT_USAGE, '这是会过期的媒体直链，请改用视频页面链接（BV 号或 watch 链接）')
    if host in BILIBILI_HOSTS:
        match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av[0-9]+)/?', parsed.path)
        if not match:
            raise FetchError(EXIT_USAGE, '只支持 B 站普通视频页面，如 https://www.bilibili.com/video/BVxxxx/')
        parts = urllib.parse.parse_qs(parsed.query, keep_blank_values=True).get('p', [])
        if parts and (len(parts) != 1 or not re.fullmatch(r'[1-9][0-9]*', parts[0])):
            raise FetchError(EXIT_USAGE, 'p 参数必须是单个正整数')
        suffix = '?p=' + parts[0] if parts else ''
        return 'bilibili', 'https://www.bilibili.com/video/' + match.group(1) + '/' + suffix
    if host in YOUTUBE_HOSTS:
        if parsed.path == '/watch':
            ids = urllib.parse.parse_qs(parsed.query).get('v', [])
            if len(ids) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{11}', ids[0]):
                return 'youtube', 'https://www.youtube.com/watch?v=' + ids[0]
        if host == 'youtu.be':
            candidate = parsed.path.strip('/')
            if re.fullmatch(r'[A-Za-z0-9_-]{11}', candidate):
                return 'youtube', 'https://www.youtube.com/watch?v=' + candidate
        raise FetchError(EXIT_USAGE, '只支持 YouTube 普通 watch 链接')
    raise FetchError(EXIT_USAGE, f'不支持的站点：{host or value}')


def resolve_short(url, *, opener=None):
    """Follow a b23.tv short link to the canonical page URL."""
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (reference-video-fetch)'})
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=20)
        final = response.geturl() if hasattr(response, 'geturl') else response
    except FetchError:
        raise
    except Exception as error:  # network errors are a usage-level failure, not a crash
        raise FetchError(EXIT_UNAVAILABLE, f'短链无法解析：{error}') from error
    try:
        response.close()
    except Exception:
        pass
    if not final:
        raise FetchError(EXIT_UNAVAILABLE, '短链没有返回真实地址')
    return final


def run_tool(command, *, runner=subprocess.run, timeout=None):
    return runner(command, capture_output=True, text=True, timeout=timeout)


def tool_version(binary, *, runner=subprocess.run):
    try:
        result = run_tool([binary, '--version'], runner=runner, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or '').strip().splitlines()[0] if result.stdout else 'unknown'


def probe(binary, page_url, *, runner=subprocess.run, timeout=60):
    command = [
        binary, '--no-warnings', '--no-playlist', '--skip-download', '--dump-single-json',
        '--socket-timeout', str(max(int(timeout / 3), 5)), '--retries', '1', page_url,
    ]
    try:
        result = run_tool(command, runner=runner, timeout=timeout)
    except FileNotFoundError as error:
        raise FetchError(EXIT_NO_TOOL, f'找不到 yt-dlp：{error}') from error
    except subprocess.SubprocessError as error:
        raise FetchError(EXIT_FAILED, f'探测失败：{error}') from error
    if result.returncode != 0 or not (result.stdout or '').strip():
        notes = classify_notes(result.stderr or '')
        raise FetchError(classify_code(result.stderr or ''), f'无法读取该页面：{first_error(result.stderr)}', notes=notes)
    try:
        return json.loads(result.stdout), classify_notes(result.stderr or '')
    except json.JSONDecodeError as error:
        raise FetchError(EXIT_FAILED, f'页面信息不是有效 JSON：{error}') from error


def first_error(stderr):
    for line in reversed((stderr or '').strip().splitlines()):
        if line.strip():
            return line.strip()[:300]
    return '未知原因'


def classify_code(stderr):
    text = (stderr or '').lower()
    if 'sign in' in text or '登录' in text or 'login' in text or 'private video' in text:
        return EXIT_UNAVAILABLE
    for marker in ('404', 'not found', 'does not exist', '不存在', '已删除', 'unavailable'):
        if marker in text:
            return EXIT_UNAVAILABLE
    if 'geo' in text or '地区' in text or 'not available in your country' in text:
        return EXIT_UNAVAILABLE
    return EXIT_FAILED


def classify_notes(stderr):
    text = stderr or ''
    lowered = text.lower()
    notes = []
    if 'premium member' in lowered or '大会员' in text:
        notes.append('高清晰度需要登录或大会员；本次只使用匿名可获得的画质')
    if 'cookies' in lowered:
        notes.append('站点提示需要 cookie 才能取更高画质；本工具不传 cookie')
    if 'geo' in lowered or '地区' in text:
        notes.append('该视频在当前网络区域不可用')
    return notes


def resolution_class(entry):
    width = entry.get('width') or 0
    height = entry.get('height') or 0
    if not width or not height:
        return 0
    return min(int(width), int(height))


def video_formats(info):
    return [f for f in (info.get('formats') or []) if (f.get('vcodec') or 'none') != 'none' and resolution_class(f)]


def audio_formats(info):
    return [f for f in (info.get('formats') or []) if (f.get('vcodec') or 'none') == 'none' and (f.get('acodec') or 'none') != 'none']


def choose_formats(info, max_height):
    """Pick one video stream and one audio stream under the anonymous ceiling."""
    videos = video_formats(info)
    if not videos:
        raise FetchError(EXIT_UNAVAILABLE, '这个页面没有可下载的视频流')
    available = max(resolution_class(f) for f in videos)
    if max_height:
        allowed = [f for f in videos if resolution_class(f) <= max_height] or [
            min(videos, key=lambda f: resolution_class(f))
        ]
    else:
        allowed = videos
    best_class = max(resolution_class(f) for f in allowed)
    pool = [f for f in allowed if resolution_class(f) == best_class]
    preferred = [f for f in pool if any(codec in (f.get('vcodec') or '') for codec in VIDEO_CODEC_PREFERENCE)]
    pool = preferred or pool
    mp4 = [f for f in pool if (f.get('ext') == 'mp4')]
    pool = mp4 or pool
    chosen = sorted(pool, key=lambda f: (f.get('fps') or 0, f.get('tbr') or 0))[0]
    audios = audio_formats(info)
    audio = None
    if audios:
        m4a = [f for f in audios if (f.get('ext') == 'm4a')]
        audio = sorted(m4a or audios, key=lambda f: (f.get('abr') or 0), reverse=True)[0]
    return chosen, audio, available


def build_command(binary, page_url, chosen, audio, target, *, timeout, limit_rate, sleep_requests):
    selector = str(chosen.get('format_id'))
    if audio:
        selector = f"{selector}+{audio.get('format_id')}"
    command = [
        binary, '--no-warnings', '--no-playlist', '--no-mtime',
        '--socket-timeout', str(max(int(timeout / 3), 5)), '--retries', '2',
        '--merge-output-format', 'mp4', '-f', selector, '-o', str(target),
    ]
    if limit_rate:
        command += ['--limit-rate', limit_rate]
    if sleep_requests:
        command += ['--sleep-requests', str(sleep_requests)]
    return command + [page_url]


def build_record(info, site, page_url, *, notes, path, selected, audio, available, requested_height, transport='no-login'):
    record = {
        'schema_version': SCHEMA_VERSION,
        'tool': 'yt-dlp',
        'site': site,
        'page_url': page_url,
        'video_id': info.get('id'),
        'title': info.get('title'),
        'uploader': info.get('uploader') or info.get('channel'),
        'duration_seconds': info.get('duration'),
        'fetched_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'transport': transport,
        'redistribution': 'local-reference-only',
        'requested_max_height': requested_height or None,
        'available_max_height': available,
        'quality_limited': bool(available and requested_height and available < requested_height),
        'selected_format_id': (selected or {}).get('format_id'),
        'audio_format_id': (audio or {}).get('format_id'),
        'path': str(path) if path else None,
        'bytes': None,
        'sha256': None,
        'width': (selected or {}).get('width'),
        'height': (selected or {}).get('height'),
        'fps': (selected or {}).get('fps'),
        'video_codec': (selected or {}).get('vcodec'),
        'audio_codec': (audio or {}).get('acodec'),
        'notes': list(notes),
    }
    return record


def describe_media(path, *, runner=subprocess.run):
    if not shutil.which('ffprobe'):
        return {}
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name,width,height,avg_frame_rate',
        '-show_entries', 'format=duration', '-of', 'json', str(path),
    ]
    try:
        result = run_tool(command, runner=runner, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    try:
        payload = json.loads(result.stdout or '{}')
    except json.JSONDecodeError:
        return {}
    summary = {}
    for stream in payload.get('streams') or []:
        if stream.get('codec_type') == 'video' and 'width' not in summary:
            summary['width'] = stream.get('width')
            summary['height'] = stream.get('height')
            summary['video_codec'] = stream.get('codec_name')
            rate = stream.get('avg_frame_rate') or ''
            match = re.fullmatch(r'(\d+)/(\d+)', str(rate))
            if match and int(match.group(2)):
                summary['fps'] = round(int(match.group(1)) / int(match.group(2)), 3)
        if stream.get('codec_type') == 'audio' and 'audio_codec' not in summary:
            summary['audio_codec'] = stream.get('codec_name')
    try:
        summary['duration_seconds'] = round(float(payload.get('format', {}).get('duration')), 3)
    except (TypeError, ValueError):
        pass
    return summary


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def media_files(directory, stem):
    files = [p for p in Path(directory).glob(stem + '.*') if p.suffix not in {'.part', '.ytdl', '.json'}]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def fetch(args, *, runner=subprocess.run, opener=None):
    site, page_url = canonical_page(args.url, opener=opener)
    binary = args.yt_dlp or shutil.which('yt-dlp')
    if not binary:
        raise FetchError(EXIT_NO_TOOL, '没有找到 yt-dlp；请安装 yt-dlp，或让用户自备参考视频文件')
    version = tool_version(binary, runner=runner)
    if not version:
        raise FetchError(EXIT_NO_TOOL, f'{binary} 无法执行 --version')
    info, notes = probe(binary, page_url, runner=runner, timeout=args.timeout)
    duration = info.get('duration') or 0
    if args.max_duration and duration and duration > args.max_duration:
        raise FetchError(
            EXIT_TOO_LONG,
            f'视频时长 {duration:.0f}s 超过上限 {args.max_duration}s；确认要取整条时显式提高 --max-duration',
        )
    chosen, audio, available = choose_formats(info, args.max_height)
    if args.require_height and available < args.require_height:
        raise FetchError(
            EXIT_QUALITY,
            f'匿名可获得的最高画质是 {available}p，低于要求的 {args.require_height}p',
            notes=notes,
        )
    if args.max_height and available < args.max_height:
        notes.append(f'匿名上限为 {available}p（请求上限 {args.max_height}p）；未使用登录态')
    record = build_record(
        info, site, page_url, notes=notes, path=None, selected=chosen, audio=audio,
        available=available, requested_height=args.max_height,
    )
    if args.probe:
        if args.record:
            write_record(args.record, record)
        return EXIT_OK, record
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = args.stem or str(info.get('id') or 'reference')
    existing = media_files(out, stem)
    if existing and not args.force:
        raise FetchError(EXIT_EXISTS, f'{existing[0]} 已存在；确认要覆盖时加 --force')
    target_template = out / (stem + '.%(ext)s')
    command = build_command(
        binary, page_url, chosen, audio, target_template,
        timeout=args.timeout, limit_rate=args.limit_rate, sleep_requests=args.sleep_requests,
    )
    try:
        result = run_tool(command, runner=runner, timeout=None)
    except OSError as error:
        raise FetchError(EXIT_NO_TOOL, f'无法执行 yt-dlp：{error}') from error
    if result.returncode != 0:
        raise FetchError(classify_code(result.stderr or ''), f'下载失败：{first_error(result.stderr)}',
                         notes=classify_notes(result.stderr or ''))
    produced = media_files(out, stem)
    if not produced:
        raise FetchError(EXIT_FAILED, 'yt-dlp 没有产出文件')
    path = produced[0]
    record['path'] = str(path)
    record['bytes'] = path.stat().st_size
    record['sha256'] = sha256_of(path)
    record.update({k: v for k, v in describe_media(path, runner=runner).items() if v is not None})
    if args.record:
        write_record(args.record, record)
    else:
        write_record(path.with_suffix(path.suffix + '.fetch.json'), record)
    return EXIT_OK, record


def write_record(path, record):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def parser():
    p = argparse.ArgumentParser(
        description='用 yt-dlp 匿名下载参考视频页面（B 站 / YouTube），并写出抓取记录。不传 cookie，不再分发。',
    )
    p.add_argument('--url', required=True, help='公开视频页面链接（BV 号页面、b23.tv 短链或 YouTube watch 链接）')
    p.add_argument('--out', default='reference', help='下载目录，默认 ./reference')
    p.add_argument('--stem', help='输出文件名主干，默认用视频 ID')
    p.add_argument('--record', help='抓取记录 JSON 路径，默认与视频同名的 .fetch.json')
    p.add_argument(
        '--max-height', type=int, default=DEFAULT_MAX_HEIGHT,
        help='可选画质上限（按短边计算）。默认 0 = 不设上限，取站点匿名可给的最高画质',
    )
    p.add_argument('--require-height', type=int, help='要求的画质下限；匿名达不到时直接失败')
    p.add_argument('--max-duration', type=int, default=DEFAULT_MAX_DURATION, help='允许的最长时长（秒），默认 900')
    p.add_argument('--limit-rate', help='限速，例如 4M')
    p.add_argument('--sleep-requests', type=float, default=1, help='请求间隔秒数，默认 1')
    p.add_argument('--timeout', type=int, default=120, help='单次工具调用的超时秒数，默认 120')
    p.add_argument('--yt-dlp', help='指定 yt-dlp 可执行文件路径')
    p.add_argument('--probe', action='store_true', help='只探测页面与可用画质，不下载')
    p.add_argument('--force', action='store_true', help='允许覆盖已存在的输出文件')
    p.add_argument('--json', action='store_true', help='以 JSON 输出结果摘要')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        code, record = fetch(args)
    except FetchError as error:
        summary = {'ok': False, 'code': error.code, 'message': error.message, 'notes': error.notes}
        print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else f'失败：{error.message}', file=sys.stderr)
        for note in error.notes:
            print(f'注意：{note}', file=sys.stderr)
        return error.code
    if args.json:
        print(json.dumps({'ok': True, **record}, ensure_ascii=False, indent=2))
    else:
        target = record['path'] or '（仅探测）'
        print(f"站点：{record['site']}｜标题：{record['title']}｜作者：{record['uploader']}")
        print(f"时长：{record['duration_seconds']}s｜采用画质：{record['available_max_height']}p｜选用格式：{record['selected_format_id']}")
        print(f"输出：{target}")
        for note in record['notes']:
            print(f'注意：{note}')
        if record.get('path'):
            print('提醒：参考视频只留在本机用于分析，不要提交到仓库或媒体库。')
    return code


if __name__ == '__main__':
    sys.exit(main())
