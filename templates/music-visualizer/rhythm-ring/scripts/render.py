#!/usr/bin/env python3
"""Render audio-reactive rings from a frozen master, without SVC or model calls."""
from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import wave

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if not low <= value <= high or (integer and value != int(value)):
        raise ValueError(f'{name} must be within {low}..{high}' + (' and integral' if integer else ''))
    return int(value) if integer else float(value)


def local_file(base, value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must name a local file')
    path = (base / value).resolve()
    if not path.is_file():
        raise ValueError(f'{name} file does not exist: {path}')
    return path


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def audio_duration(path, stream):
    duration = stream.get('duration')
    if duration is not None:
        return number(float(duration), 'audio duration', 0.001, 86400)
    # Some containers omit stream durations. Measure decoded audio, not video length.
    with tempfile.TemporaryDirectory(prefix='ring-duration-') as tmp:
        decoded = Path(tmp) / 'duration.wav'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(path),
                        '-map', '0:a:0', '-vn', '-af', 'asetpts=PTS-STARTPTS,aresample=8000',
                        '-ac', '1', '-c:a', 'pcm_s16le', str(decoded)], check=True)
        with wave.open(str(decoded), 'rb') as wav:
            return number(wav.getnframes() / wav.getframerate(), 'audio duration', 0.001, 86400)


def load_project(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(cfg, dict) or cfg.get('schema_version') != 1:
        raise ValueError('Expected schema_version 1 project object')
    allowed = {'schema_version', 'audio', 'audio_sha256', 'image', 'font', 'output', 'width',
               'height', 'fps', 'start', 'duration', 'title', 'credit', 'colors', 'cues'}
    if set(cfg) - allowed:
        raise ValueError('Unknown project fields: ' + ', '.join(sorted(set(cfg) - allowed)))
    for name in ('audio', 'image', 'font'):
        cfg[name] = local_file(path.parent, cfg.get(name), name)
    with Image.open(cfg['image']) as image:
        image.verify()
    ImageFont.truetype(str(cfg['font']), 24)
    expected = cfg.get('audio_sha256')
    if not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('audio_sha256 must be the lowercase SHA-256 of the approved master')
    if sha256(cfg['audio']) != expected:
        raise ValueError('Audio SHA-256 mismatch; approve the new master and retime cues first')
    cfg['width'] = number(cfg.get('width', 1080), 'width', 240, 3840, True)
    cfg['height'] = number(cfg.get('height', 1920), 'height', 240, 3840, True)
    if cfg['width'] % 2 or cfg['height'] % 2:
        raise ValueError('width and height must be even for yuv420p')
    cfg['fps'] = number(cfg.get('fps', 60), 'fps', 1, 60, True)
    cfg['start'] = number(cfg.get('start', 0), 'start', 0, 86400)
    info = probe(cfg['audio'])
    audio = next((s for s in info['streams'] if s.get('codec_type') == 'audio'), None)
    if audio is None:
        raise ValueError('Input has no audio stream')
    total = audio_duration(cfg['audio'], audio)
    remaining = total - cfg['start']
    cfg['duration'] = number(cfg.get('duration', remaining), 'duration', 0.1, 3600)
    if cfg['duration'] > remaining + 1e-6:
        raise ValueError('Requested segment exceeds the source audio')
    cfg['frames'] = math.ceil(cfg['duration'] * cfg['fps'])
    for field in ('title', 'credit'):
        cfg[field] = cfg.get(field, '')
        if not isinstance(cfg[field], str) or '\n' in cfg[field] or len(cfg[field]) > 120:
            raise ValueError(f'{field} must be one line, at most 120 characters')
    colors = cfg.get('colors', ['#69E0CD', '#FF799A'])
    if not isinstance(colors, list) or len(colors) != 2:
        raise ValueError('colors must contain two RGB hex colors')
    for color in colors:
        if not isinstance(color, str) or len(color) != 7 or not color.startswith('#'):
            raise ValueError('colors must contain RGB hex colors')
        ImageColor.getrgb(color)
    cfg['colors'] = colors
    cfg['cues'] = cfg.get('cues', [])
    if not isinstance(cfg['cues'], list):
        raise ValueError('cues must be an array')
    previous_end = 0.0
    for cue in cfg['cues']:
        if not isinstance(cue, dict) or set(cue) != {'start', 'end', 'lines'}:
            raise ValueError('Each cue needs only start, end, lines')
        start = number(cue['start'], 'cue start', 0, cfg['duration'])
        end = number(cue['end'], 'cue end', 0, cfg['duration'])
        if end <= start or start < previous_end:
            raise ValueError('Cues must be ordered, non-overlapping, positive intervals')
        if not isinstance(cue['lines'], list) or not 1 <= len(cue['lines']) <= 2:
            raise ValueError('Each cue needs one or two lines')
        if any(not isinstance(line, str) or not line.strip() or '\n' in line or len(line) > 120 for line in cue['lines']):
            raise ValueError('Cue lines must be nonempty, at most 120 characters, without newlines')
        previous_end = end
    raw_output = cfg.get('output')
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ValueError('output must be a new .mp4 path')
    cfg['output'] = (path.parent / raw_output).resolve()
    if cfg['output'].suffix.lower() != '.mp4':
        raise ValueError('output must end in .mp4')
    cfg['record'] = cfg['output'].with_suffix('.render.json')
    if cfg['output'].exists() or cfg['record'].exists():
        raise ValueError('Output or render record already exists; choose a new version')
    if cfg['output'] in (cfg['audio'], cfg['image'], cfg['font'], path):
        raise ValueError('Output must not overwrite an input')
    cfg['project'] = path
    cfg['project_sha256'] = sha256(path)
    return cfg


def rms_envelope(path, fps, frames):
    """Per-frame stereo energy, without phase-cancelling mono downmix."""
    values = []
    with wave.open(str(path), 'rb') as wav:
        if wav.getsampwidth() != 2 or wav.getcomptype() != 'NONE':
            raise ValueError('Analysis WAV must be PCM16')
        rate = wav.getframerate()
        for frame in range(frames):
            count = ((frame + 1) * rate // fps) - (frame * rate // fps)
            samples = array('h', wav.readframes(count))
            if sys.byteorder != 'little':
                samples.byteswap()
            values.append(math.sqrt(sum(x * x for x in samples) / len(samples)) / 32768 if samples else 0.0)
    # Absolute floor prevents near-silent masters from driving a full-scale pulse.
    scale = max(0.02, sorted(values)[min(len(values) - 1, int(len(values) * 0.95))])
    smoothed, state = [], 0.0
    for value in values:
        target = min(1.0, value / scale)
        tau = 0.025 if target > state else 0.14
        alpha = 1 - math.exp(-1 / (fps * tau))
        state += alpha * (target - state)
        smoothed.append(state)
    return smoothed


def decode_analysis(cfg, path, low_band=False):
    filters = segment_filter(cfg)
    filters += ',lowpass=f=180,aresample=8000' if low_band else ',aresample=8000'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(cfg['audio']),
                    '-map', '0:a:0',
                    '-vn', '-af', filters, '-ac', '2', '-c:a', 'pcm_s16le', str(path)], check=True)
    with wave.open(str(path), 'rb') as wav:
        available = wav.getnframes() / wav.getframerate()
    if available + 0.03 < cfg['duration']:
        raise ValueError('Decoded audio is shorter than the requested segment')
    return rms_envelope(path, cfg['fps'], cfg['frames'])


def segment_filter(cfg):
    return (f"asetpts=PTS-STARTPTS,atrim=start={cfg['start']}:duration={cfg['duration']},"
            'asetpts=PTS-STARTPTS')


def stop_encoder(process):
    if process.stdin and not process.stdin.closed:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def fitted_font(font_path, text, width, size):
    for current in range(size, 7, -1):
        font = ImageFont.truetype(str(font_path), current)
        if font.getlength(text) <= width:
            return font
    raise ValueError('Text cannot fit; shorten it or split it into two cue lines')


def canvas(cfg):
    w, h = cfg['width'], cfg['height']
    base = Image.new('RGB', (w, h), '#17191D')
    with Image.open(cfg['image']) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        # Preserve the whole supplied illustration as the background.
        fitted = ImageOps.contain(image, (w, h))
        base.paste(fitted, ((w - fitted.width) // 2, (h - fitted.height) // 2))
    shade = Image.new('RGB', (w, h), '#000000')
    return Image.blend(base, shade, 0.22)


def draw_frame(cfg, base, frame, full, low):
    image = base.copy()
    draw = ImageDraw.Draw(image)
    w, h = image.size
    unit = min(w, h)
    ring_unit = min(unit, h * 0.67)
    cx, cy = w * 0.5, h * 0.48
    for index, energy in enumerate((low, full)):
        radius = ring_unit * (0.285 + index * 0.045 + energy * 0.027)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     outline=cfg['colors'][index], width=max(1, round(unit * (0.003 + energy * 0.004))))
    text_rows = [(cfg['title'], h * 0.12, round(unit * 0.065)),
                 (cfg['credit'], h * 0.19, round(unit * 0.034))]
    time = frame / cfg['fps']
    for cue in cfg['cues']:
        if cue['start'] <= time < cue['end']:
            text_rows.extend((line, h * (0.81 + i * 0.055), round(unit * 0.045))
                             for i, line in enumerate(cue['lines']))
            break
    for text, y, size in text_rows:
        if text:
            font = fitted_font(cfg['font'], text, w * 0.86, size)
            draw.text((w / 2, y), text, font=font, anchor='mm', fill='white',
                      stroke_width=max(1, round(unit * 0.002)), stroke_fill='#151515')
    return image


def render(cfg):
    output = cfg['output']
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='ring-', dir=output.parent) as tmp:
        tmp = Path(tmp)
        # All passes consume the same private bytes even if the source path is edited.
        cfg = dict(cfg)
        for name in ('audio', 'image', 'font'):
            snapshot = tmp / (name + cfg[name].suffix)
            shutil.copyfile(cfg[name], snapshot)
            cfg[name] = snapshot
        if sha256(cfg['audio']) != cfg['audio_sha256']:
            raise ValueError('Audio changed before snapshot; approve the master again')
        full = decode_analysis(cfg, tmp / 'full.wav')
        low = decode_analysis(cfg, tmp / 'low.wav', True)
        base = canvas(cfg)
        # Validate all text before spawning the encoder, including late cues.
        for frame in [0, *(math.ceil(c['start'] * cfg['fps']) for c in cfg['cues'])]:
            draw_frame(cfg, base, frame, 0, 0)
        silent = tmp / 'picture.mp4'
        command = ['ffmpeg', '-nostdin', '-v', 'error', '-n', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                   '-s', f"{cfg['width']}x{cfg['height']}", '-r', str(cfg['fps']), '-i', 'pipe:0',
                   '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                   '-threads', '2', str(silent)]
        with (tmp / 'encoder.log').open('w+') as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log, bufsize=0)
            try:
                for frame in range(cfg['frames']):
                    payload = memoryview(draw_frame(cfg, base, frame, full[frame], low[frame]).tobytes())
                    while payload:
                        written = process.stdin.write(payload)
                        if not written:
                            raise BrokenPipeError('Encoder input closed before the frame was written')
                        payload = payload[written:]
                process.stdin.close()
                if process.wait(timeout=60) != 0:
                    log.seek(0)
                    raise RuntimeError(log.read())
            finally:
                stop_encoder(process)
        final = tmp / 'final.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-n', '-i', str(silent),
                        '-i', str(cfg['audio']), '-map', '0:v:0', '-map', '1:a:0', '-af', segment_filter(cfg),
                        '-t', str(cfg['duration']), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
                        '-ar', '48000', '-ac', '2', '-movflags', '+faststart', str(final)], check=True)
        info = probe(final)
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        if (video['width'], video['height']) != (cfg['width'], cfg['height']):
            raise RuntimeError('Output dimensions differ from project')
        if abs(float(info['format']['duration']) - cfg['duration']) > max(0.1, 1 / cfg['fps']):
            raise RuntimeError('Output duration differs from project')
        if abs(float(audio.get('start_time', 0))) > 0.05 or abs(float(audio['duration']) - cfg['duration']) > 0.05:
            raise RuntimeError('Output audio timing differs from the requested segment')
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', str(final),
                        '-f', 'null', '-'], check=True)
        record = {'schema_version': 1, 'project_sha256': cfg['project_sha256'],
                  'audio_sha256': cfg['audio_sha256'], 'image_sha256': sha256(cfg['image']),
                  'font_sha256': sha256(cfg['font']), 'source_start': cfg['start'],
                  'duration': cfg['duration'], 'fps': cfg['fps'], 'frames': int(video['nb_frames']),
                  'width': cfg['width'], 'height': cfg['height'], 'cues': cfg['cues'],
                  'analysis': 'stereo RMS; full band and lowpass 180Hz; not beat detection or FFT',
                  'audio_codec': audio['codec_name'], 'output_sha256': sha256(final),
                  'elapsed_seconds': round(time.monotonic() - started, 3),
                  'full_decode_passed': True, 'visual_review': 'not_performed'}
        # Exclusive creation keeps pre-existing versions intact, including races.
        with output.open('xb') as target, final.open('rb') as source:
            shutil.copyfileobj(source, target)
        with cfg['record'].open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate files, master hash and cues without rendering')
    args = parser.parse_args(argv)
    try:
        cfg = load_project(args.project)
        result = {'valid': True, 'frames': cfg['frames'], 'duration': cfg['duration']} if args.check else render(cfg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f'Render error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
