#!/usr/bin/env python3
"""Bounded, metadata-only voice-line discovery. Candidates are not training approval."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from urllib.parse import parse_qs, urlsplit


LANGUAGES = {
    'zh-CN': ('中文语音', ('中文', '中配', '普通话', 'chinese', 'mandarin', 'zh-cn')),
    'ja-JP': ('日本語 ボイス', ('日语', '日文', '日配', '日本語', 'japanese', 'ja-jp')),
    'en-US': ('English voice lines', ('英语', '英文', '英配', 'english', 'en-us')),
    'ko-KR': ('한국어 음성', ('韩语', '韩文', '韩配', '한국어', 'korean', 'ko-kr')),
}
NON_SOURCE = ('翻唱', 'ai cover', 'voice conversion', 'rvc', 'ddsp', '攻略', '挂机',
              '模组任务', '实况', '同人配音', 'fandub', 'voice clone')


def normalized(text):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', text).casefold())


def text_field(value, name, optional=False):
    if optional and value is None:
        return ''
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f'{name} must contain 1..200 characters')
    if any(unicodedata.category(char).startswith('C') for char in value):
        raise ValueError(f'{name} contains control characters')
    return value.strip()


def canonical_url(value):
    """Keep page identifiers, not signed media URLs, credentials or arbitrary hosts."""
    if not isinstance(value, str):
        raise ValueError('Candidate needs a supported public page URL')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port:
        raise ValueError('Only normal public HTTP(S) page URLs are supported')
    host = (parsed.hostname or '').lower()
    if host in ('www.bilibili.com', 'bilibili.com', 'm.bilibili.com'):
        match = re.fullmatch(r'/video/(BV[A-Za-z0-9]{10}|av[0-9]+)/?', parsed.path)
        if match:
            parts = parse_qs(parsed.query, keep_blank_values=True).get('p', [])
            if parts and (len(parts) != 1 or not re.fullmatch(r'[1-9][0-9]*', parts[0])):
                raise ValueError('Bilibili p must be one positive integer')
            suffix = '?p=' + parts[0] if parts else ''
            return 'bilibili', 'https://www.bilibili.com/video/' + match.group(1) + '/' + suffix
    if host in ('www.youtube.com', 'youtube.com', 'm.youtube.com') and parsed.path == '/watch':
        ids = parse_qs(parsed.query).get('v', [])
        if len(ids) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{11}', ids[0]):
            return 'youtube', 'https://www.youtube.com/watch?v=' + ids[0]
    if host == 'youtu.be' and re.fullmatch(r'/[A-Za-z0-9_-]{11}', parsed.path):
        return 'youtube', 'https://www.youtube.com/watch?v=' + parsed.path[1:]
    raise ValueError('Use a Bilibili video or YouTube watch page, not a media/download URL')


def candidate(raw, provider, identity):
    if not isinstance(raw, dict) or (raw.get('title') is not None and not isinstance(raw['title'], str)):
        raise ValueError('Incomplete candidate metadata')
    url = raw.get('webpage_url') or raw.get('url')
    if provider == 'youtube' and isinstance(url, str) and re.fullmatch(r'[A-Za-z0-9_-]{11}', url):
        url = 'https://www.youtube.com/watch?v=' + url
    site, url = canonical_url(url)
    if site != provider:
        raise ValueError('Candidate host does not match requested provider')
    title = (raw.get('title') or '')[:1000]
    description = raw.get('description') if isinstance(raw.get('description'), str) else ''
    haystack = normalized(title + ' ' + description[:10000])
    language = identity['language']
    language_matches = [code for code, (_, hints) in LANGUAGES.items()
                        if any(normalized(hint) in haystack for hint in hints)]
    matches = {
        'character': any(normalized(name) in haystack for name in [identity['character'], *identity['aliases']]),
        'series': normalized(identity['series']) in haystack,
        'language': language in language_matches,
        'actor': normalized(identity['actor']) in haystack if identity['actor'] else None,
    }
    blockers = []
    if haystack and not matches['character']:
        blockers.append('character_not_found_in_metadata')
    if language_matches and language not in language_matches:
        blockers.append('different_language_in_metadata')
    if len(language_matches) > 1:
        blockers.append('multiple_languages_require_manual_segmentation')
    if any(normalized(word) in normalized(title) for word in NON_SOURCE):
        blockers.append('cover_gameplay_or_fandub_title')
    duration = raw.get('duration')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        duration = None
    uploader = raw.get('uploader')
    return {
        'provider': provider, 'url': url, 'title': title,
        'uploader': uploader[:300] if isinstance(uploader, str) else None,
        'duration_seconds': duration, 'metadata_matches': matches,
        'needs_details': not title or not matches['language'] or (bool(identity['actor']) and not matches['actor']),
        'blockers': blockers, 'review_priority': sum(value is True for value in matches.values()),
        'official_recording_status': 'unverified', 'hosting_authority': 'unverified',
        'training_rights': 'unknown', 'ready_for_training': False,
        'next_step': ('Use --inspect-url to resolve this URL-only result before evaluating its identity.' if not title else
                      'Inspect the page and recording; metadata is not proof of speaker, origin or rights.'),
    }


def search_command(binary, provider, query, limit, inspect_url=None):
    prefix = 'bilisearch' if provider == 'bilibili' else 'ytsearch'
    args = [binary, '--ignore-config', '--no-plugin-dirs', '--no-cache-dir',
            '--no-js-runtimes', '--no-remote-components',
            '--skip-download', '--dump-single-json', '--no-progress', '--socket-timeout', '10',
            '--retries', '1', '--extractor-retries', '1', '--encoding', 'utf-8']
    if inspect_url:
        args += ['--no-playlist', inspect_url]
    else:
        args += ['--flat-playlist', '--playlist-end', str(limit), f'{prefix}{limit}:{query}']
    return args


def decode_candidates(payload, provider, identity, limit):
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError('Expected a metadata JSON object')
    entries = data.get('entries', [data])
    if not isinstance(entries, list):
        raise ValueError('Expected a metadata entry array')
    found, rejected, urls = [], 0, set()
    for raw in entries[:limit]:
        try:
            item = candidate(raw, provider, identity)
        except (ValueError, TypeError):
            rejected += 1
            continue
        if item['url'] not in urls:
            urls.add(item['url'])
            found.append(item)
    return found, rejected


def discover(identity, providers, *, binary='yt-dlp', limit=8, timeout=90, inspect_url=None, run=subprocess.run):
    if identity['language'] not in LANGUAGES:
        raise ValueError('Unsupported helper language; use the native search workflow for other languages')
    if not providers or any(site not in ('bilibili', 'youtube') for site in providers):
        raise ValueError('Unsupported provider')
    query = ' '.join(filter(None, (identity['series'], identity['character'],
                                  LANGUAGES[identity['language']][0], identity['actor'])))
    attempts, candidates = [], []
    for provider in providers:
        command = search_command(binary, provider, query, limit, inspect_url)
        attempt = {'provider': provider, 'query': query, 'mode': 'inspect' if inspect_url else 'search',
                   'status': 'pending', 'candidate_count': 0}
        # No user cookies/config/cache or media writes; discard raw signed-URL metadata.
        with tempfile.TemporaryDirectory(prefix='voice-metadata-') as tmp:
            try:
                result = run(command, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, encoding='utf-8', timeout=timeout, check=False)
                if result.returncode != 0:
                    error = (result.stderr or '').lower()
                    kinds = [('unrecognized', 'tool_incompatible'), ('no such option', 'tool_incompatible'),
                             ('403', 'access_denied'), ('412', 'access_denied'), ('429', 'rate_limited'),
                             ('sign in', 'authentication_required'), ('captcha', 'challenge_required')]
                    kind = next((label for marker, label in kinds if marker in error), 'network_or_extractor_error')
                    attempt.update(status='provider_error', exit_code=result.returncode, error_kind=kind)
                else:
                    items, rejected = decode_candidates(result.stdout, provider, identity, limit)
                    candidates.extend(items)
                    attempt.update(status='partial_metadata' if rejected else 'ok',
                                   candidate_count=len(items), rejected_entries=rejected)
            except FileNotFoundError:
                attempt['status'] = 'tool_missing'
            except subprocess.TimeoutExpired:
                attempt['status'] = 'timeout'
            except (ValueError, TypeError, OSError, UnicodeError):
                attempt['status'] = 'invalid_metadata_or_tool_error'
        attempts.append(attempt)
    candidates.sort(key=lambda item: (bool(item['blockers']), -item['review_priority'], item['url']))
    reviewable = [item for item in candidates if not item['blockers']]
    incomplete = any(attempt['status'] != 'ok' for attempt in attempts)
    return {
        'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
        'identity': identity, 'query': query, 'attempts': attempts, 'candidates': candidates,
        'status': 'candidates_need_review' if reviewable else ('search_incomplete' if incomplete else 'no_matching_candidates'),
        'search_complete': not incomplete, 'media_downloaded': False, 'metadata_is_untrusted': True,
        'ready_for_training': False,
        'next_step': ('Review recording identity, source chain and rights before downloading.' if reviewable else
                      'Complete native official/wiki search routes or fix the tool error before requesting user materials.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character', required=True)
    parser.add_argument('--series', required=True)
    parser.add_argument('--language', required=True, choices=LANGUAGES)
    parser.add_argument('--actor')
    parser.add_argument('--alias', action='append', default=[])
    parser.add_argument('--provider', choices=('bilibili', 'youtube', 'both'), default='bilibili')
    parser.add_argument('--inspect-url', help='Read full metadata of one supported candidate page, without downloading')
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--yt-dlp', default='yt-dlp', help='Existing local yt-dlp executable')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.limit <= 10 or not 10 <= args.timeout <= 180:
            raise ValueError('limit must be 1..10 and timeout 10..180 seconds per provider')
        identity = {'character': text_field(args.character, 'character'),
                    'series': text_field(args.series, 'series'), 'language': args.language,
                    'actor': text_field(args.actor, 'actor', optional=True),
                    'aliases': [text_field(alias, 'alias') for alias in args.alias]}
        output = args.output.absolute()
        if output.exists() or output.is_symlink():
            raise ValueError('Discovery report already exists; select a new attempt filename')
        providers = ['bilibili', 'youtube'] if args.provider == 'both' else [args.provider]
        url = None
        if args.inspect_url:
            provider, url = canonical_url(args.inspect_url)
            providers = [provider]
        installed = shutil.which(args.yt_dlp)
        binary = str(Path(installed).resolve()) if installed else args.yt_dlp
        report = discover(identity, providers, binary=binary, limit=args.limit,
                          timeout=args.timeout, inspect_url=url)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'status': report['status'], 'candidate_count': len(report['candidates']),
                          'search_complete': report['search_complete'], 'media_downloaded': False}, ensure_ascii=False))
        return 0 if report['search_complete'] else 1
    except (ValueError, OSError) as exc:
        print(f'Discovery error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
