#!/usr/bin/env python3
"""Explicit, offline-first character showcase editing. Default action only plans."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# Historical Python Hermite values: tangents are already normalized to u, not frames.
SCALE_KFS = (
    (0.0, 312.0, -6.120207911535838, -6.120207911535838),
    (123.0, 222.0, -27.796610169488954, -27.796610169488954),
    (186.268, 222.0, -27.796610169488954, -27.796610169488954),
    (310.733, 104.0, -9.562927856583157, -9.562927856583157),
)


def hermite(y0, y1, m0, m1, u):
    u = max(0.0, min(1.0, u))
    return ((2*u**3 - 3*u**2 + 1)*y0 + (u**3 - 2*u**2 + u)*m0
            + (-2*u**3 + 3*u**2)*y1 + (u**3 - u**2)*m1)


def scale_at(frame, fps=60, speed=1.0):
    rel = max(0.0, frame * 60 / fps * speed)
    for left, right in zip(SCALE_KFS, SCALE_KFS[1:]):
        if rel <= right[0]:
            return hermite(left[1], right[1], left[3], right[2],
                           (rel-left[0])/(right[0]-left[0]))
    return 104.0


def blur_at(frame, fps=60):
    # Scale speed deliberately does not accelerate blur.
    return 45.0 * max(0.0, 1.0 - max(0.0, frame) * 60 / fps / 91.117)


def number(value, label, minimum=0, maximum=1e9, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label}: finite number required')
    if not minimum <= value <= maximum or (integer and value != int(value)):
        raise ValueError(f'{label}: expected {minimum}..{maximum}' + (' integer' if integer else ''))
    return int(value) if integer else float(value)


def keys(obj, allowed, label):
    if not isinstance(obj, dict):
        raise ValueError(f'{label}: object required')
    unknown = set(obj) - set(allowed)
    if unknown:
        raise ValueError(f'{label}: unsupported fields {sorted(unknown)}')


def path_value(value, root, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value or '://' in value:
        raise ValueError(f'{label}: local file path required')
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def distributed(total, count):
    bounds = [round(i * total / count) for i in range(count+1)]
    return bounds, [b-a for a, b in zip(bounds, bounds[1:])]


def make_plan(data, root=Path('.'), require_files=False):
    keys(data, {'schema_version', 'mode', 'canvas', 'output', 'clips', 'total_frames',
                'transition_frames', 'intro_frames', 'intro_blur_frames', 'end_fade_frames', 'layout', 'audio'}, 'manifest')
    if data.get('schema_version') != 1 or isinstance(data.get('schema_version'), bool):
        raise ValueError('schema_version must be 1')
    mode = data.get('mode')
    if mode not in {'A', 'B', 'C', 'D'}:
        raise ValueError('mode must be A, B, C or D')
    canvas = data.get('canvas', {})
    keys(canvas, {'width', 'height', 'fps'}, 'canvas')
    width = number(canvas.get('width', 1080), 'width', 2, 8192, True)
    height = number(canvas.get('height', 1920), 'height', 2, 8192, True)
    fps = number(canvas.get('fps', 60), 'fps', 1, 120, True)
    if width % 2 or height % 2:
        raise ValueError('canvas dimensions must be even for yuv420p')
    transition = number(data.get('transition_frames', round((25 if mode in 'AB' else 30)*fps/60)),
                        'transition_frames', 0, 1200, True)
    if mode == 'A' and transition != round(25*fps/60):
        raise ValueError('A preserves the historical 25/60-second foreground transition; use B/C/D for custom transitions')
    layout = data.get('layout', {})
    keys(layout, {'mode', 'fit'}, 'layout')
    layout = {'mode': layout.get('mode', 'plain' if mode == 'D' else 'blurred'),
              'fit': layout.get('fit', 'contain')}
    if layout['mode'] not in {'plain', 'blurred', 'blurred-fill'} or layout['fit'] not in {'contain', 'cover'}:
        raise ValueError('layout.mode=plain|blurred|blurred-fill; layout.fit=contain|cover')
    if mode in 'AC' and layout['mode'] != 'blurred':
        raise ValueError('A/C require blurred layout: C keeps the same 104% foreground scale across image/video joins')
    source = data.get('clips')
    if not isinstance(source, list) or not 1 <= len(source) <= 64:
        raise ValueError('clips: explicit ordered list of 1..64 inputs required')
    clips, seen = [], set()
    for index, raw in enumerate(source):
        keys(raw, {'id', 'kind', 'path', 'pair_id', 'frames', 'scale_speed', 'source_duration_seconds',
                   'source_start_seconds', 'source_take_seconds', 'speed'}, f'clips[{index}]')
        cid = raw.get('id')
        if not isinstance(cid, str) or not cid.strip() or cid in seen:
            raise ValueError('clip ids must be nonempty and unique')
        seen.add(cid)
        kind = raw.get('kind')
        if kind not in {'image', 'video'} or (mode in 'AB' and kind != 'image') or (mode == 'D' and kind != 'video'):
            raise ValueError(f'clip {cid}: kind incompatible with mode {mode}')
        clip = {'id': cid, 'kind': kind, 'path': str(path_value(raw.get('path'), root, cid))}
        clip['exists'] = Path(clip['path']).is_file()
        if require_files and not clip['exists']:
            raise ValueError(f'missing input: {clip["path"]}')
        if kind == 'image':
            if any(k in raw for k in ('source_duration_seconds', 'source_start_seconds', 'source_take_seconds', 'speed')):
                raise ValueError(f'{cid}: video timing fields cannot be used on an image')
            if mode in 'AB' and any(k in raw for k in ('frames', 'scale_speed')):
                raise ValueError(f'{mode} uses total_frames and its fixed motion rules')
            clip['scale_speed'] = number(raw.get('scale_speed', 1), 'scale_speed', .1, 10)
            if mode == 'C':
                clip['frames'] = number(raw.get('frames'), f'{cid}.frames', 1, 216000, True)
        else:
            if 'frames' in raw or 'scale_speed' in raw:
                raise ValueError(f'{cid}: videos cannot use still frames/scale_speed')
            duration = number(raw.get('source_duration_seconds'), f'{cid}.source_duration_seconds', .001, 86400)
            start = number(raw.get('source_start_seconds', 0), f'{cid}.source_start_seconds', 0, duration)
            take = number(raw.get('source_take_seconds', duration-start), f'{cid}.source_take_seconds', .001, duration)
            if start + take > duration + 1e-9:
                raise ValueError(f'{cid}: selected source window exceeds declared duration')
            speed = number(raw.get('speed', 1), f'{cid}.speed', .1, 10)
            clip.update(source_duration_seconds=duration, source_start_seconds=start,
                        source_take_seconds=take, speed=speed, frames=round(take/speed*fps))
            if clip['frames'] < 1:
                raise ValueError(f'{cid}: duration rounds to zero output frames')
        if mode == 'C':
            clip['pair_id'] = raw.get('pair_id')
        elif 'pair_id' in raw:
            raise ValueError('pair_id is only supported in mode C')
        clips.append(clip)
    if mode == 'C':
        if len(clips) % 2:
            raise ValueError('C requires image/video pairs')
        pairs = set()
        for first, second in zip(clips[::2], clips[1::2]):
            pair = first.get('pair_id')
            if first['kind'] != 'image' or second['kind'] != 'video' or not isinstance(pair, str) or not pair or pair != second.get('pair_id') or pair in pairs:
                raise ValueError('C requires unique pair_id and adjacent image -> matching video order')
            pairs.add(pair)
    if mode in 'AB':
        total = number(data.get('total_frames'), 'total_frames', 1, 216000, True)
        bounds, lengths = distributed(total + ((len(clips)-1)*transition if mode == 'B' else 0), len(clips))
        for clip, frames in zip(clips, lengths):
            clip['frames'] = frames
    else:
        if 'total_frames' in data:
            raise ValueError('C/D compute duration from clip lengths minus overlaps; omit total_frames')
        total = sum(c['frames'] for c in clips) - (len(clips)-1)*transition
        bounds = None
    # Prevent ambiguous triple overlaps and clips completely consumed by transitions.
    for i, clip in enumerate(clips):
        minimum = transition * (2 if 0 < i < len(clips)-1 and mode != 'A' else 1)
        if clip['frames'] <= minimum and len(clips) > 1:
            raise ValueError(f'{clip["id"]}: clip too short for transition windows')
    if not 1 <= total <= 216000:
        raise ValueError('total length must be 1..216000 frames')
    intro = number(data.get('intro_frames', round(50*fps/60) if mode == 'B' else 0), 'intro_frames', 0, total, True)
    intro_blur = number(data.get('intro_blur_frames', 0), 'intro_blur_frames', 0, total, True)
    end = number(data.get('end_fade_frames', fps if mode == 'A' else round(fps/2) if mode in 'CD' else 0),
                 'end_fade_frames', 0, total, True)
    if intro + end > total:
        raise ValueError('intro and end fade windows overlap')
    cursor, offsets = 0, []
    for i, clip in enumerate(clips):
        if mode == 'A':
            clip['start_frame'] = bounds[i]
        else:
            clip['start_frame'] = cursor
            if i:
                offsets.append(cursor)
            cursor += clip['frames'] - (transition if i < len(clips)-1 else 0)
    audio = data.get('audio', {'mode': 'silent'})
    keys(audio, {'mode', 'path', 'source_start_seconds', 'output_start_seconds', 'gain_db', 'loop', 'source_gain_db'}, 'audio')
    if audio.get('mode') not in {'silent', 'bgm', 'source', 'source+bgm'}:
        raise ValueError('audio.mode must be silent, bgm, source or source+bgm')
    if audio['mode'] in {'source', 'source+bgm'} and mode not in 'CD':
        raise ValueError('source audio is only meaningful for C/D')
    source_gain = number(audio.get('source_gain_db', 0), 'source_gain_db', -60, 12)
    if audio['mode'] in {'bgm', 'silent'} and 'source_gain_db' in audio:
        raise ValueError('source_gain_db requires source or source+bgm')
    if audio['mode'] == 'silent':
        if set(audio) != {'mode'}:
            raise ValueError('silent audio accepts no music settings')
        audio = {'mode': 'silent'}
    elif audio['mode'] == 'source':
        if set(audio) - {'mode', 'source_gain_db'}:
            raise ValueError('source mode accepts only source_gain_db')
        audio = {'mode': 'source', 'source_gain_db': source_gain}
    else:
        if not isinstance(audio.get('loop', True), bool):
            raise ValueError('audio.loop must be boolean')
        audio = {'mode': audio['mode'], 'path': str(path_value(audio.get('path'), root, 'audio.path')),
                 'source_start_seconds': number(audio.get('source_start_seconds', 0), 'audio source start', 0, 86400),
                 'output_start_seconds': number(audio.get('output_start_seconds', 0), 'audio output start', 0, total/fps),
                 'gain_db': number(audio.get('gain_db', -7), 'audio gain_db', -60, 12), 'loop': audio.get('loop', True)}
        if audio['mode'] == 'source+bgm':
            audio['source_gain_db'] = source_gain
        if audio['output_start_seconds'] >= total/fps:
            raise ValueError('BGM must start before output ends')
        audio['exists'] = Path(audio['path']).is_file()
        if require_files and not audio['exists']:
            raise ValueError(f'missing BGM: {audio["path"]}')
    output = path_value(data.get('output'), root, 'output')
    if output.suffix.lower() != '.mp4':
        raise ValueError('output must end in .mp4')
    report = output.with_suffix('.render.json')
    if output.exists() or report.exists():
        raise ValueError('output or success manifest already exists; choose a new output name')
    sources = [Path(c['path']) for c in clips] + ([Path(audio['path'])] if 'path' in audio else [])
    if output in sources or report in sources:
        raise ValueError('output conflicts with an input')
    result = {'schema_version': 1, 'status': 'planned', 'mode': mode, 'canvas': {'width': width, 'height': height, 'fps': fps},
              'layout': layout, 'clips': clips, 'total_frames': total, 'duration_seconds': total/fps,
              'transition_frames': transition, 'intro_frames': intro, 'intro_blur_frames': intro_blur, 'end_fade_frames': end,
              'transition_offsets_frames': offsets, 'audio': audio, 'output': str(output), 'report': str(report)}
    if mode == 'A':
        pre = round(12*fps/60)
        post = transition-pre
        result.update(boundaries_frames=bounds, transition_pre_frames=pre, transition_post_frames=post,
                      background_delay_frames=post+max(1, round(fps/60)))
    return result


def a_layers(frame, plan):
    bounds = plan['boundaries_frames']
    for index, boundary in enumerate(bounds[1:-1]):
        if boundary-plan['transition_pre_frames'] <= frame < boundary+plan['transition_post_frames']:
            u = (frame-boundary+plan['transition_pre_frames'])/plan['transition_frames']
            return [(index, frame-bounds[index], 1-u), (index+1, max(0, frame-boundary), u)]
    index = min(len(bounds)-2, max(0, bisect.bisect_right(bounds, frame)-1))
    return [(index, frame-bounds[index], 1.0)]


def a_background(frame, plan):
    return sum(frame >= b+plan['background_delay_frames'] for b in plan['boundaries_frames'][1:-1])


def fitted_size(source_width, source_height, box_width, box_height, fit='contain', scale=1):
    ratio = (min if fit == 'contain' else max)(box_width/source_width, box_height/source_height) * scale
    return max(1, round(source_width*ratio)), max(1, round(source_height*ratio))


def run(command):
    subprocess.run([str(x) for x in command], check=True)


def ffmpeg():
    return ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-n', '-filter_complex_threads', '1']


def encoder():
    return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart']


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], text=True))


def preflight_media(plan):
    fps = plan['canvas']['fps']
    for clip in plan['clips']:
        if clip['kind'] != 'video':
            clip['has_audio'] = False
            continue
        streams = probe(clip['path'])['streams']
        video = next((s for s in streams if s['codec_type'] == 'video' and not s.get('disposition', {}).get('attached_pic')), None)
        if video is None:
            raise ValueError(f'{clip["id"]}: no video stream')
        clip['video_stream_index'] = number(video.get('index'), 'video stream index', 0, 65535, True)
        clip['has_audio'] = any(s['codec_type'] == 'audio' for s in streams)
        if video.get('sample_aspect_ratio', '1:1') not in {'1:1', 'N/A', '0:1'}:
            raise ValueError(f'{clip["id"]}: normalize non-square source pixels before editing')
        duration = float(video.get('duration', 'nan'))
        if not math.isfinite(duration) or abs(duration-clip['source_duration_seconds']) > 1/fps+.02:
            raise ValueError(f'{clip["id"]}: declared source duration differs from video stream; update the plan')
        if clip['source_start_seconds']+clip['source_take_seconds'] > duration+1/fps:
            raise ValueError(f'{clip["id"]}: source window exceeds actual video')
    audio = plan['audio']
    if 'path' in audio:
        streams = probe(audio['path'])['streams']
        stream = next((s for s in streams if s['codec_type'] == 'audio'), None)
        if stream is None:
            raise ValueError('BGM has no audio stream')
        duration = float(stream.get('duration', 'nan'))
        if not math.isfinite(duration):
            raise ValueError('BGM stream needs a measurable duration')
        if audio['source_start_seconds'] >= duration:
            raise ValueError('BGM source start exceeds actual duration')
        if not audio['loop'] and duration-audio['source_start_seconds'] < plan['duration_seconds']-audio['output_start_seconds']:
            raise ValueError('BGM too short with loop=false; shorten output or explicitly enable looping')


def image_helpers(plan):
    from PIL import Image, ImageFilter, ImageOps
    width, height = plan['canvas']['width'], plan['canvas']['height']
    fit, layout = plan['layout']['fit'], plan['layout']['mode']
    def load(path):
        with Image.open(path) as source:
            return ImageOps.exif_transpose(source).convert('RGB')
    def resize(image, scale, background=False):
        if background:
            # Preserve the original 236%-of-width square scale, expanding only if needed to fill.
            ratio = max(width/image.width, height/image.height)
            if layout == 'blurred':
                ratio = max(ratio, width*2.36/max(image.size))
            size = (max(1, round(image.width*ratio)), max(1, round(image.height*ratio)))
        else:
            box = (width, width) if layout == 'blurred' else (width, height)
            size = fitted_size(*image.size, *box, fit, scale)
        return image.resize(size, Image.Resampling.LANCZOS)
    def center(canvas, image, opacity=1):
        layer = image.convert('RGBA')
        if opacity < 1:
            layer.putalpha(round(255*max(0, opacity)))
        canvas.alpha_composite(layer, ((width-layer.width)//2, (height-layer.height)//2))
    def background(image):
        frame = Image.new('RGBA', (width, height), 'black')
        if layout != 'plain':
            sigma = (35 if layout == 'blurred-fill' else 40)*width/1080
            center(frame, resize(image, 1, True).filter(ImageFilter.GaussianBlur(sigma)))
        return frame
    def foreground(image, frame, animated=False, speed=1):
        scale = scale_at(frame, plan['canvas']['fps'], speed)/100 if animated else (1.04 if layout == 'blurred' else 1)
        layer = resize(image, scale)
        blur = blur_at(frame, plan['canvas']['fps'])*width/1080 if animated else 0
        return layer.filter(ImageFilter.GaussianBlur(blur)) if blur > .05 else layer
    return load, center, background, foreground


def write_frames(frames, count, plan, destination):
    c = plan['canvas']
    command = ffmpeg()+['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{c["width"]}x{c["height"]}',
                       '-r', str(c['fps']), '-i', 'pipe:0', '-frames:v', str(count), '-an']+encoder()+[str(destination)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            process.stdin.write(frame.convert('RGB').tobytes())
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('FFmpeg frame encoding failed')
    except BaseException:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
        process.wait()
        raise


def render_images(plan, work):
    load, center, background, foreground = image_helpers(plan)
    if plan['mode'] == 'A':
        images = [load(c['path']) for c in plan['clips']]
        backgrounds = [background(image) for image in images]
        def frames():
            for f in range(plan['total_frames']):
                frame = backgrounds[a_background(f, plan)].copy()
                for index, rel, opacity in a_layers(f, plan):
                    center(frame, foreground(images[index], rel, True), opacity)
                yield frame
        destination = work/'a-silent.mp4'
        write_frames(frames(), plan['total_frames'], plan, destination)
        return [destination]
    parts = []
    for i, clip in enumerate(plan['clips']):
        destination = work/f'{i:03d}.mp4'
        if clip['kind'] == 'video':
            render_video(clip, plan, destination)
        else:
            image = load(clip['path'])
            bg = background(image)
            if plan['mode'] == 'B':
                center(bg, foreground(image, 0))
                still = work/f'{i:03d}.png'
                bg.convert('RGB').save(still)
                run(ffmpeg()+['-loop', '1', '-framerate', str(plan['canvas']['fps']), '-i', str(still),
                              '-frames:v', str(clip['frames']), '-an']+encoder()+[destination])
            else:
                def frames():
                    for f in range(clip['frames']):
                        frame = bg.copy()
                        center(frame, foreground(image, f, True, clip['scale_speed']))
                        yield frame
                write_frames(frames(), clip['frames'], plan, destination)
        parts.append(destination)
    return parts


def video_filter(clip, plan):
    c = plan['canvas']
    width, height, fps = c['width'], c['height'], c['fps']
    fit = 'decrease' if plan['layout']['fit'] == 'contain' else 'increase'
    start, take, speed = clip['source_start_seconds'], clip['source_take_seconds'], clip['speed']
    stream = str(clip['video_stream_index']) if 'video_stream_index' in clip else 'V:0'
    head = f'[0:{stream}]trim=start={start}:duration={take},setpts=(PTS-STARTPTS)/{speed},fps={fps},setsar=1'
    if plan['layout']['mode'] == 'plain':
        sizing = (f'scale={width}:{height}:force_original_aspect_ratio={fit}:flags=lanczos,'
                  + (f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2' if fit == 'decrease' else f'crop={width}:{height}'))
        return head+','+sizing+',format=yuv420p[vout]'
    if plan['layout']['mode'] == 'blurred-fill':
        return (head+',split=2[bg0][fg0];'
                f'[bg0]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},gblur=sigma={35*width/1080}[bg];'
                f'[fg0]scale={width}:{height}:force_original_aspect_ratio={fit}:flags=lanczos[fg];'
                '[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]')
    box = round(width*1.04)
    bgbox = round(width*2.36)
    return (head+',split=2[bg0][fg0];'
            f'[bg0]scale=w=\'iw*max({bgbox}/max(iw,ih),max({width}/iw,{height}/ih))\':h=-1:flags=lanczos,'
            f'crop={width}:{height},gblur=sigma={40*width/1080}[bg];'
            f'[fg0]scale={box}:{box}:force_original_aspect_ratio={fit}:flags=lanczos[fg];'
            '[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]')


def render_video(clip, plan, destination):
    run(ffmpeg()+['-i', clip['path'], '-filter_complex', video_filter(clip, plan), '-map', '[vout]',
                  '-frames:v', str(clip['frames']), '-an']+encoder()+[destination])


def compose_command(plan, parts, destination):
    command = ffmpeg()
    fps, total = plan['canvas']['fps'], plan['duration_seconds']
    filters = []
    for i, part in enumerate(parts):
        command += ['-i', str(part)]
        filters.append(f'[{i}:v]fps={fps},settb=AVTB,setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]')
    current = 'v0'
    transition = plan['transition_frames']/fps
    for i in range(1, len(parts)):
        out = f'join{i}'
        if transition:
            offset = plan['transition_offsets_frames'][i-1]/fps
            filters.append(f'[{current}][v{i}]xfade=transition=fade:duration={transition:.12f}:offset={offset:.12f}[{out}]')
        else:
            filters.append(f'[{current}][v{i}]concat=n=2:v=1:a=0[{out}]')
        current = out
    if plan['intro_blur_frames']:
        duration = plan['intro_blur_frames']/fps
        filters += [f'[{current}]split=2[intro-sharp][intro-base]',
                    f'[intro-base]gblur=sigma={30*plan["canvas"]["width"]/1080}[intro-blurred]',
                    f"[intro-blurred][intro-sharp]blend=all_expr='A*(1-min(T/{duration:.12f},1))+B*min(T/{duration:.12f},1)'[intro-ready]"]
        current = 'intro-ready'
    tail = f'[{current}]trim=end_frame={plan["total_frames"]},setpts=PTS-STARTPTS'
    if plan['intro_frames']:
        tail += f',fade=t=in:st=0:d={plan["intro_frames"]/fps:.12f}'
    if plan['end_fade_frames']:
        fade = plan['end_fade_frames']/fps
        tail += f',fade=t=out:st={max(0, total-fade-1/fps):.12f}:d={fade:.12f}'
    filters.append(tail+'[vout]')
    audio = plan['audio']
    next_input = len(parts)
    if audio['mode'] in {'source', 'source+bgm'}:
        for i, clip in enumerate(plan['clips']):
            length = clip['frames']/fps
            if clip['kind'] == 'video' and clip.get('has_audio'):
                command += ['-i', clip['path']]
                start = clip['source_start_seconds']
                take = clip['source_take_seconds']
                af = (f'[{next_input}:a:0]atrim=start={start}:duration={take},asetpts=PTS-STARTPTS,'
                      f'{atempo_chain(clip["speed"])},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,')
                next_input += 1
            else:
                af = 'anullsrc=r=48000:cl=stereo,'
            filters.append(af+f'apad,atrim=duration={length:.12f},asetpts=PTS-STARTPTS[source{i}]')
        acurrent = 'source0'
        for i in range(1, len(plan['clips'])):
            out = f'asource{i}'
            cross = f'acrossfade=d={transition:.12f}:c1=tri:c2=tri' if transition else 'concat=n=2:v=0:a=1'
            filters.append(f'[{acurrent}][source{i}]{cross}[{out}]')
            acurrent = out
        filters.append(f'[{acurrent}]volume={audio["source_gain_db"]}dB,atrim=duration={total:.12f}[natural]')
    if 'path' in audio:
        if audio['loop']:
            command += ['-stream_loop', '-1']
        command += ['-i', audio['path']]
        delay_samples = round(audio['output_start_seconds']*48000)
        audible = total-audio['output_start_seconds']
        af = (f'[{next_input}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
              f'atrim=start={audio["source_start_seconds"]}:duration={audible:.12f},asetpts=PTS-STARTPTS,'
              f'volume={audio["gain_db"]}dB,adelay={delay_samples}S:all=1,apad,atrim=duration={total:.12f}')
        filters.append(af+'[music]')
    if audio['mode'] != 'silent':
        if audio['mode'] == 'source+bgm':
            filters.append('[natural][music]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.95:level=0:latency=1[mixed]')
            afinal = 'mixed'
        else:
            afinal = 'natural' if audio['mode'] == 'source' else 'music'
        finish = f'[{afinal}]apad,atrim=duration={total:.12f}'
        if plan['end_fade_frames']:
            finish += f',afade=t=out:st={max(0, total-plan["end_fade_frames"]/fps-1/fps):.12f}:d={plan["end_fade_frames"]/fps:.12f}'
        filters.append(finish+'[aout]')
    command += ['-filter_complex', ';'.join(filters), '-map', '[vout]']
    command += ['-map', '[aout]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2'] if audio['mode'] != 'silent' else ['-an']
    return command+['-frames:v', str(plan['total_frames']), '-t', f'{total:.12f}']+encoder()+[str(destination)]


def atempo_chain(speed):
    stages = []
    while speed > 2:
        stages.append(2.0)
        speed /= 2
    while speed < .5:
        stages.append(.5)
        speed /= .5
    stages.append(speed)
    return ','.join(f'atempo={s:.12f}' for s in stages)


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def render(plan):
    for binary in ('ffmpeg', 'ffprobe'):
        if not shutil.which(binary):
            raise ValueError(f'{binary} is required for --render')
    preflight_media(plan)
    output, report = Path(plan['output']), Path(plan['report'])
    output.parent.mkdir(parents=True, exist_ok=True)
    # The lock serializes contenders for this output; temporary files are never shared.
    lock = output.with_suffix('.render.lock')
    with lock.open('x') as handle:
        handle.write(str(os.getpid()))
    try:
        if output.exists() or report.exists():
            raise ValueError('output became occupied; choose a new output name')
        with tempfile.TemporaryDirectory(prefix='.showcase-', dir=output.parent) as directory:
            work = Path(directory)
            parts = render_images(plan, work)
            provisional = work/'complete.mp4'
            run(compose_command(plan, parts, provisional))
            streams = probe(provisional)['streams']
            video = next(s for s in streams if s['codec_type'] == 'video')
            if int(video.get('nb_frames', -1)) != plan['total_frames']:
                raise ValueError('encoded frame count differs from planned timeline; output not published')
            if (video.get('width'), video.get('height')) != (plan['canvas']['width'], plan['canvas']['height']):
                raise ValueError('encoded canvas differs from plan')
            if video.get('sample_aspect_ratio') != '1:1':
                raise ValueError('encoded sample aspect ratio must be 1:1')
            if bool([s for s in streams if s['codec_type'] == 'audio']) != (plan['audio']['mode'] != 'silent'):
                raise ValueError('encoded audio presence differs from plan')
            result = dict(plan, status='rendered_awaiting_user_review', output_sha256=file_hash(provisional),
                          verification={'encoder_exit_zero': True, 'frame_count': int(video['nb_frames']),
                                        'visual_review': False, 'audio_listening': False})
            result['input_sha256'] = {c['id']: file_hash(c['path']) for c in plan['clips']}
            if 'path' in plan['audio']:
                result['bgm_sha256'] = file_hash(plan['audio']['path'])
            success = work/'render.json'
            success.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            # Atomic, no-clobber publication on the same filesystem. No success report on failure.
            os.link(provisional, output)
            try:
                os.link(success, report)
            except BaseException:
                output.unlink()
                raise
            return result
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--plan', action='store_true', help='configuration and timeline only; missing planned inputs allowed (default)')
    group.add_argument('--check', action='store_true', help='also require input files; no media decode/render')
    group.add_argument('--render', action='store_true', help='explicitly run Pillow and FFmpeg; never starts generation models')
    args = parser.parse_args()
    try:
        data = json.loads(args.manifest.read_text(encoding='utf-8'))
        plan = make_plan(data, args.manifest.resolve().parent, require_files=args.check or args.render)
        result = render(plan) if args.render else dict(plan, status='files_checked' if args.check else 'planned')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, RuntimeError, ImportError, subprocess.SubprocessError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
