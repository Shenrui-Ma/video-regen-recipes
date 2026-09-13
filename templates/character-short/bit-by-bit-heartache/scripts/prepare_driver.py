#!/usr/bin/env python3
"""Verify the frozen historical driver and prepare four video-only H3 references.

Python 3.9+, FFmpeg and ffprobe. No ComfyUI, network or GPU calls.
This prepares reference media; it does not generate a new character.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

EXPECTED_SHA256 = 'e63386ab88bf4a11dc2fd859b0075099229cad44d77366a220c6e0bb0ba0ca0d'
RANGES = [(0, 158), (151, 309), (302, 443), (436, 577)]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path, ffprobe='ffprobe'):
    result = subprocess.run([
        ffprobe, '-v', 'error', '-count_frames', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,avg_frame_rate,nb_read_frames',
        '-of', 'json', str(path),
    ], check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout)['streams']
    if not streams:
        raise ValueError('Input has no video stream')
    video = streams[0]
    return {'width': int(video['width']), 'height': int(video['height']),
            'frames': int(video['nb_read_frames']), 'fps': video['avg_frame_rate']}


def validate_master(metadata, digest):
    if (metadata['frames'], metadata['width'], metadata['height']) != (577, 1344, 768):
        raise ValueError('Expected the historical 577-frame, 1344x768 driver. '
                         'A 578/579-frame reconstruction is a different input; do not trim it silently.')
    if Fraction(metadata['fps']) != 24:
        raise ValueError('Expected exactly 24 fps')
    if digest != EXPECTED_SHA256:
        raise ValueError('Historical driver SHA256 mismatch; use the pinned reference asset')


def segment_command(ffmpeg, source, output, start, end):
    return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
            '-i', str(source), '-map', '0:v:0', '-an',
            '-vf', f'trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS',
            '-r', '24', '-vsync', 'cfr', '-c:v', 'libx264', '-preset', 'medium',
            '-crf', '0', '-pix_fmt', 'yuv420p', '-map_metadata', '-1',
            '-map_chapters', '-1', '-movflags', '+faststart', str(output)]


def prepare(source, output_dir, ffmpeg='ffmpeg', ffprobe='ffprobe'):
    source = Path(source).resolve()
    digest = sha256(source)
    metadata = probe(source, ffprobe)
    validate_master(metadata, digest)
    output_dir = Path(output_dir).resolve()
    # Never overwrite an old run, including a partially completed one.
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': 1, 'input_sha256': digest, 'input': metadata,
                'reference_audio_connected': False,
                'scope': 'Lossless video slices of the frozen driver. Original historical '
                         'segments included AAC; these video-only files have different file hashes. '
                         'This is reference preparation, not H3 inference.',
                'segments': []}
    for index, (start, end) in enumerate(RANGES, 1):
        path = output_dir / f'seg{index}_ref24_1344x768.mp4'
        subprocess.run(segment_command(ffmpeg, source, path, start, end), check=True)
        actual = probe(path, ffprobe)
        if (actual['frames'], actual['width'], actual['height'], Fraction(actual['fps'])) != (
                end - start, 1344, 768, Fraction(24)):
            raise ValueError(f'Segment {index} failed its frame/shape/fps contract: {actual}')
        subprocess.run([ffmpeg, '-v', 'error', '-xerror', '-nostdin', '-i', str(path),
                        '-map', '0:v:0', '-f', 'null', '-'], check=True)
        manifest['segments'].append({'segment': index, 'path': path.name,
                                     'interval': [start, end], **actual,
                                     'sha256': sha256(path), 'full_decode': True})
    with (output_dir / 'reference-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Downloaded heartache-driver-577f.mp4')
    parser.add_argument('--output-dir', type=Path, help='New directory, outside the recipe checkout')
    parser.add_argument('--check-only', action='store_true', help='Validate input without writing output')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    args = parser.parse_args()
    if not args.check_only and args.output_dir is None:
        parser.error('--output-dir is required unless --check-only is set')
    if args.check_only:
        digest = sha256(args.input)
        metadata = probe(args.input, args.ffprobe)
        validate_master(metadata, digest)
        print(json.dumps({'verified': True, 'sha256': digest, **metadata}, indent=2))
    else:
        print(json.dumps(prepare(args.input, args.output_dir, args.ffmpeg, args.ffprobe), indent=2))


if __name__ == '__main__':
    main()
