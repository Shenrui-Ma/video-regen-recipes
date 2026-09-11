#!/usr/bin/env python3
"""Compile a product storyboard to an integer-frame timeline; no media execution."""
import argparse
import json
from pathlib import Path


def integer(value, label, minimum=0, maximum=18000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{label}: expected integer {minimum}..{maximum}')
    return value


def compile_plan(data):
    if not isinstance(data, dict):
        raise ValueError('Storyboard must be a JSON object')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    output = data['output']
    fps = integer(output['fps'], 'fps', 1, 120)
    width = integer(output['width'], 'width', 64, 4096)
    height = integer(output['height'], 'height', 64, 4096)
    if width % 2 or height % 2:
        raise ValueError('Video dimensions must be even')
    scenes = data['scenes']
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 32:
        raise ValueError('Expected 1..32 scenes')
    ids, timeline, cursor, previous_overlap = set(), [], 0, 0
    for index, scene in enumerate(scenes):
        sid = scene['id']
        if not isinstance(sid, str) or not sid.strip() or sid in ids:
            raise ValueError('Scene IDs must be nonempty and unique')
        ids.add(sid)
        for key in ('claim', 'evidence', 'visual_change'):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f'{sid}: {key} is required')
        frames = integer(scene['frames'], sid+'.frames', 1)
        overlap = integer(scene.get('overlap_out_frames', 0), sid+'.overlap')
        if index == len(scenes)-1 and overlap:
            raise ValueError('Last scene cannot overlap a nonexistent next scene')
        if previous_overlap+overlap >= frames:
            raise ValueError('Transitions consume the scene; leave a stable reading interval')
        beats = scene['beats']
        if not isinstance(beats, list) or not beats:
            raise ValueError('At least one intentional beat is required')
        end = 0
        for beat in beats:
            start = integer(beat['start_frame'], 'beat start')
            finish = integer(beat['end_frame'], 'beat end', 1)
            if start < end or finish <= start or finish > frames:
                raise ValueError('Beat intervals must be ordered, non-overlapping and within their scene')
            if not isinstance(beat.get('intent'), str) or not beat['intent'].strip():
                raise ValueError('Every beat needs an intent')
            end = finish
        timeline.append({**scene, 'start_frame':cursor, 'end_frame':cursor+frames,
                         'start_seconds':cursor/fps, 'duration_seconds':frames/fps})
        cursor += frames-overlap
        previous_overlap = overlap
    integer(cursor, 'total_frames', 1)
    if cursor/fps > 600:
        raise ValueError('Renderer supports at most 600 seconds')
    return {'schema_version':1, 'product':data.get('product'), 'output':output,
            'total_frames':cursor, 'duration_seconds':cursor/fps, 'scenes':timeline,
            'assets':data.get('assets', []), 'status':'planned',
            'note':'Author film.html from these timings; this compiler does not generate HTML or media.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('storyboard', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    try:
        result = compile_plan(json.loads(args.storyboard.read_text(encoding='utf-8')))
        text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(text)
        else:
            print(text, end='')
    except (ValueError, KeyError, TypeError, OSError) as error:
        p.exit(2, f'plan: {error}\n')


if __name__ == '__main__':
    main()
