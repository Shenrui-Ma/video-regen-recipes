#!/usr/bin/env python3
"""Standalone character input preparation. No service lifecycle or private tools."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import os
import re
import ipaddress
import socket
import urllib.parse
import urllib.request
from PIL import Image, ImageOps

MAX_BYTES = 32 * 1024 * 1024


def validate_public_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('Use a public HTTP(S) URL without credentials')
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('URL must resolve only to public IP addresses')
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_public(url):
    validate_public_url(url)
    # No proxy credentials, cookies, or authorization are inherited.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), PublicRedirect())
    return opener.open(urllib.request.Request(url, headers={'User-Agent': 'HeartacheCharacter/1'}), timeout=30)


def bounded_copy(stream, dest):
    total = 0
    with Path(dest).open('xb') as f:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_BYTES:
                raise ValueError('Image exceeds 32 MiB limit')
            f.write(block)


def safe_output_dir(value):
    path = Path(value).expanduser().absolute()
    # macOS /var and /tmp may themselves be system symlinks; canonicalize
    # those prefixes, but reject user-controlled directory symlinks.
    system_links = {Path('/var'), Path('/tmp'), Path('/etc')}
    if '..' in path.parts:
        raise ValueError('Output path cannot contain ..')
    for part in (path, *path.parents):
        if part.is_symlink() and part not in system_links:
            raise ValueError('Output directory cannot traverse symlinks')
    return path.resolve()


ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.part')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def image_to_png(source, out, background='#FFFFFF'):
    with Image.open(source) as image:
        if image.format not in ('PNG', 'JPEG'):
            raise ValueError('Only decoded PNG/JPEG images are accepted')
        image.verify()
    with Image.open(source) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        has_alpha = 'A' in image.getbands() or 'transparency' in image.info
        if has_alpha:
            # Dropping alpha exposes hidden RGB pixels; explicitly blend first.
            image = Image.alpha_composite(Image.new('RGBA', image.size, background), image.convert('RGBA')).convert('RGB')
        else:
            image = image.convert('RGB')
        with Path(out).open('xb') as stream:
            image.save(stream, format='PNG')
        return {'background': background, 'alpha_composited': has_alpha,
                'output_mode': image.mode, 'output_size': list(image.size)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--image', help='User-provided local PNG/JPEG; no image generation')
    inputs.add_argument('--url', help='Verified official character artwork URL; download only')
    parser.add_argument('--sha256', help='Expected source SHA256')
    parser.add_argument('--rights-note', default='User-supplied; permission not independently verified')
    parser.add_argument('--background', default='#FFFFFF', help='Solid #RRGGBB for transparency (default: #FFFFFF); output is always H3-safe RGB')
    parser.add_argument('--out-dir', required=True, help='New output directory')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', args.background):
        raise ValueError('Background must be exactly #RRGGBB (quote the value in your shell)')
    if args.sha256 and not re.fullmatch(r'[0-9a-f]{64}', args.sha256):
        raise ValueError('SHA256 must be exactly 64 lowercase hex characters')
    out = safe_output_dir(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    source = Path(args.image).expanduser().resolve(strict=True) if args.image else out / 'download.part'
    if args.url:
        try:
            with open_public(args.url) as stream:
                bounded_copy(stream, source)
            if args.sha256 and digest(source) != args.sha256:
                raise ValueError('Source SHA256 mismatch')
        except Exception:
            source.unlink(missing_ok=True)
            raise
    if args.sha256 and digest(source) != args.sha256:
        raise ValueError('Source SHA256 mismatch')
    try:
        preprocessing = image_to_png(source, out / 'character.png', args.background)
    except Exception:
        if args.url:
            source.unlink(missing_ok=True)
        raise
    with Image.open(source) as image:
        ext = '.png' if image.format == 'PNG' else '.jpg'
    shutil.copyfile(source, out / ('source' + ext))
    source_hash = digest(source)
    if args.url:
        source.unlink()
    provenance = {'status': 'complete', 'source': {'kind': 'url' if args.url else 'local', 'location': args.url or str(source), 'sha256': source_hash, 'rights_note': args.rights_note}, 'style_change': False, 'character': {'path': 'character.png', 'sha256': digest(out / 'character.png')}}
    provenance['preprocessing'] = preprocessing
    write_json(out / 'provenance.json', provenance)
    print(json.dumps({'status': 'complete', 'character': str(out / 'character.png'), 'provenance': str(out / 'provenance.json')}))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
