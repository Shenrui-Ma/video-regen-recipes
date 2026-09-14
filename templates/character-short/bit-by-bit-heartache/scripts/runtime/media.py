"""CPU-only reference slicing, checkpoint inspection, and continuous-music assembly."""
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from graphs import TEMPLATE
from local_io import digest
from prepare_driver import probe, segment_command
from run_segment import atomic_json


def full_decode(path):
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(path),
                    '-map', '0', '-f', 'null', '-'], check=True)


def preflight_media():
    """Exercise the runner's actual PATH tools, not an encoder-name listing."""
    try:
        with tempfile.TemporaryDirectory(prefix='heartache-aac-') as tmp:
            output = Path(tmp) / 'aac.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-n',
                            '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
                            '-af', 'atrim=start=0:end=0.25,asetpts=PTS-STARTPTS,afade=t=out:st=0:d=0.25',
                            '-c:a', 'aac', '-b:a', '320k', '-ar', '44100', '-ac', '2', '-t', '0.25',
                            '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart',
                            str(output)], check=True, capture_output=True, text=True, timeout=30)
            meta = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                              '-show_streams', '-of', 'json', str(output)], timeout=30))
            tracks = meta['streams']
            if (len(tracks) != 1 or tracks[0]['codec_name'] != 'aac'
                    or tracks[0]['sample_rate'] != '44100' or tracks[0]['channels'] != 2):
                raise ValueError('AAC_PREFLIGHT_STREAM_CONTRACT')
            full_decode(output)
            return {key: tracks[0][key] for key in ('codec_name', 'sample_rate', 'channels')} | {
                'full_decode': True, 'inference': False}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        raise ValueError("FFMPEG_AAC_PREFLIGHT_FAILED: " + detail.strip() +
                         "; select a compatible FFmpeg/ffprobe via the runner PATH; "
                         "no sampling was authorized by this check") from exc


def prepare_references(source, directory, rows):
    source, directory = Path(source), Path(directory)
    meta = probe(source)
    if Fraction(meta['fps']) != 24 or rows[-1]['timeline_end'] > meta['frames']:
        raise ValueError('DRIVER_MUST_BE_24FPS_WITH_ENOUGH_FRAMES')
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for row in rows:
        start = row['timeline_start'] - row['head_trim_frames']
        if start < 0:
            raise ValueError('REFERENCE_CONTEXT_BEFORE_START')
        end = min(start + row['sample_frames'], meta['frames'])
        pad = row['sample_frames'] - (end - start)
        output = directory / f"seg{row['segment']:02d}.mp4"
        cmd = segment_command('ffmpeg', source, output, start, end)
        if pad:
            i = cmd.index('-vf') + 1
            cmd[i] += f",tpad=stop_mode=clone:stop={pad},trim=end_frame={row['sample_frames']}"
        subprocess.run(cmd, check=True)
        actual = probe(output)
        if actual != {**meta, 'frames': row['sample_frames']}:
            raise ValueError('REFERENCE_MEDIA_CONTRACT')
        full_decode(output)
        records.append({'file': output.name, 'segment': row['segment'], 'driver_start': start,
                        'driver_end': end, 'padded_frames': pad, **actual,
                        'sha256': digest(output), 'full_decode': True})
    atomic_json(directory / 'manifest.json', {'segments': records, 'source_sha256': digest(source),
                                              'inference': False})
    return records


def validate_latent(path, part):
    """Inspect safetensors without torch/GPU; only the verified F32 Core format."""
    path = Path(path)
    with path.open('rb') as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError('LATENT_HEADER')
        length = struct.unpack('<Q', prefix)[0]
        if length > 16 * 1024 * 1024 or length > path.stat().st_size - 8:
            raise ValueError('LATENT_HEADER_SIZE')
        header = json.loads(stream.read(length))
    tensor = header.get('latent_tensor', {})
    shape = tensor.get('shape', [])
    expected_rank = 5 if part == 'video' else 4
    channels = 24 if part == 'video' else 32
    if ('latent_format_version_0' not in header or tensor.get('dtype') != 'F32'
            or len(shape) != expected_rank or shape[:2] != [1, channels]
            or any(type(x) is not int or x < 1 for x in shape)
            or (part == 'audio' and shape[2] != 2)):
        raise ValueError('LATENT_FORMAT_OR_SHAPE')
    offset = tensor['data_offsets']
    if offset[0] < 0 or offset[1] - offset[0] != math.prod(shape) * 4:
        raise ValueError('LATENT_OFFSETS')
    ends = [item['data_offsets'][1] for key, item in header.items() if key != '__metadata__']
    if length + 8 + max(ends) != path.stat().st_size:
        raise ValueError('LATENT_TRUNCATED_OR_EXTRA_BYTES')
    return tensor


def validate_segment_latent(path, part, sample_frames, width=1344, height=768):
    tensor = validate_latent(path, part)
    if type(sample_frames) is not int or sample_frames < 5 or sample_frames % 17 != 5:
        raise ValueError('LATENT_SAMPLE_FRAME_GRID')
    # Core nodes_minimax_h3.temporal_shape: 17m+5 -> 5m+2 video;
    # audio uses round(frame_count / 24 * 40), NOT truncation.
    expected = ([1, 24, (sample_frames - 5) // 17 * 5 + 2, height // 16, width // 16]
                if part == 'video' else [1, 32, 2, round(Fraction(sample_frames * 40, 24))])
    if tensor['shape'] != expected:
        raise ValueError('LATENT_SEGMENT_SHAPE')
    return tensor


def verify_video(path, frames, width=1344, height=768, audio=False):
    p = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames',
                    '-show_streams', '-show_format', '-of', 'json', str(path)]))
    videos = [s for s in p['streams'] if s['codec_type'] == 'video']
    tracks = [s for s in p['streams'] if s['codec_type'] == 'audio']
    if len(videos) != 1 or len(tracks) != int(audio):
        raise ValueError('MEDIA_STREAM_COUNT')
    video = videos[0]
    if (int(video['nb_read_frames']), video['width'], video['height'], Fraction(video['avg_frame_rate'])) != (frames, width, height, Fraction(24)):
        raise ValueError('PUBLISHED_VIDEO_CONTRACT')
    if abs(float(video['duration']) - frames / 24) > .003:
        raise ValueError('VIDEO_DURATION')
    if audio and (abs(float(tracks[0]['duration']) - frames / 24) > .03
                  or tracks[0]['sample_rate'] != '44100' or tracks[0]['channels'] != 2):
        raise ValueError('CONTINUOUS_AUDIO_CONTRACT')
    full_decode(path)
    return {'frames': frames, 'width': width, 'height': height, 'fps': 24,
            'duration': frames / 24, 'audio_tracks': len(tracks), 'full_decode': True, 'sha256': digest(path)}


def video_hash(path):
    return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0',
                                    '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-'], text=True).strip()


def decoded_frame_hashes(path):
    text = subprocess.check_output(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(path),
                                    '-map', '0:v:0', '-an', '-vsync', '0', '-pix_fmt', 'yuv420p',
                                    '-f', 'framehash', '-hash', 'sha256', '-'], text=True)
    # Timestamps and H264 packet representations may change on remux; pixels must not.
    return [line.rsplit(',', 1)[1].strip() for line in text.splitlines() if line and not line.startswith('#')]


def _publish_media(path, command, verify):
    """Publish only verified media, atomically and without clobbering a target."""
    if path.is_symlink():
        raise ValueError('UNKNOWN_EXISTING_ASSEMBLY')
    if path.exists():
        try:
            return verify(path)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            raise ValueError('EXISTING_ASSEMBLY_MEDIA_INVALID: ' + path.name +
                             '; preserve the old artifacts and use a new assembly directory '
                             'with the same SHA-verified published inputs; do not resample') from exc
    # An exclusively created directory proves ownership of cleanup targets.
    # Never unlink a pre-existing .part merely because its name looks familiar.
    with tempfile.TemporaryDirectory(dir=path.parent, prefix='.' + path.name + '-') as tmp:
        part = Path(tmp) / (path.name + '.part')
        subprocess.run(command + ['-f', 'mp4', str(part)], check=True)
        receipt = verify(part)
        # Same-filesystem hard link publishes atomically without replacing any target.
        os.link(part, path)
        return receipt


def assemble(published, music, directory, rows, width=1344, height=768):
    if len(published) != len(rows) or not rows:
        raise ValueError('PUBLISHED_SEGMENT_COUNT')
    for index, row in enumerate(rows):
        if row['segment'] != index + 1 or row['timeline_start'] != (rows[index - 1]['timeline_end'] if index else 0):
            raise ValueError('NONCONTIGUOUS_PUBLISH_PLAN')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    inputs = [{'sha256': digest(p), 'visible_frames': row['visible_frames']}
              for p, row in zip(published, rows)]
    identity = {'inputs': inputs, 'music_sha256': digest(music), 'rows': rows, 'width': width, 'height': height}
    allowed = {'assembly-intent.json', 'concat.txt', 'silent.mp4', 'final.mp4', 'verification.json'}
    if any(path.name not in allowed or path.is_symlink() or not path.is_file()
           for path in directory.iterdir()):
        raise ValueError('UNKNOWN_EXISTING_ASSEMBLY')
    intent = directory / 'assembly-intent.json'
    if intent.exists():
        if json.loads(intent.read_text()) != identity:
            raise ValueError('ASSEMBLY_INPUT_CHANGED')
    else:
        if any(directory.iterdir()):
            raise ValueError('UNKNOWN_EXISTING_ASSEMBLY')
        atomic_json(intent, identity)
    verification = directory / 'verification.json'
    if verification.exists():
        previous = json.loads(verification.read_text())
        final = directory / 'final.mp4'
        if (previous.get('identity') != identity or not final.is_file()
                or digest(final) != previous.get('sha256')):
            raise ValueError('COMPLETED_ASSEMBLY_CHANGED')
    for path, row in zip(published, rows):
        verify_video(path, row['visible_frames'], width, height, audio=False)
    listing = directory / 'concat.txt'
    lines = []
    for path, row in zip(published, rows):
        filename = str(Path(path).resolve())
        if '\n' in filename or '\r' in filename:
            raise ValueError('UNSAFE_CONCAT_FILENAME')
        lines.append("file '" + filename.replace("'", "'\\''") + "'\nduration " + f"{row['visible_frames']/24:.9f}\n")
    listing.write_text(''.join(lines), encoding='utf-8')
    frames = sum(row['visible_frames'] for row in rows)
    input_hashes = [value for path in published for value in decoded_frame_hashes(path)]
    if len(input_hashes) != frames:
        raise ValueError('CONCAT_DECODED_FRAMES_CHANGED')

    def verify_assembly(path, audio=False):
        receipt = verify_video(path, frames, width, height, audio=audio)
        if decoded_frame_hashes(path) != input_hashes:
            raise ValueError('CONCAT_DECODED_FRAMES_CHANGED')
        return receipt

    silent = directory / 'silent.mp4'
    _publish_media(silent, ['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-n', '-f', 'concat',
                          '-safe', '0', '-i', str(listing), '-map', '0:v:0', '-an', '-c:v', 'copy',
                          '-movflags', '+faststart'],
                   verify_assembly)
    final = directory / 'final.mp4'
    duration = frames / 24
    fade = min(.5, duration)
    af = f'atrim=start=0:end={duration:.9f},asetpts=PTS-STARTPTS,afade=t=out:st={duration-fade:.9f}:d={fade:.9f}'
    receipt = _publish_media(final, ['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-n',
                            '-i', str(silent), '-i', str(music),
                            '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-af', af,
                            '-c:a', 'aac', '-b:a', '320k', '-ar', '44100', '-ac', '2', '-t', f'{duration:.9f}',
                            '-map_metadata', '-1', '-map_chapters', '-1', '-movflags', '+faststart'],
                             lambda path: verify_assembly(path, audio=True))
    receipt.update(decoded_frames_match_inputs=True, decoded_frame_count=len(input_hashes),
                   packet_hash_matches_silent=video_hash(silent) == video_hash(final))
    receipt.update(identity=identity, file='final.mp4', clean_install_inference_verified=False,
                   visual_alignment_verified=False, audio_policy='one continuous original music track after published-only concat')
    atomic_json(directory / 'verification.json', receipt)
    return receipt
