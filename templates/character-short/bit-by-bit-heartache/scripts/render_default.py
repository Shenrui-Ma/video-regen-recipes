#!/usr/bin/env python3
"""Validate the bundled editing sources; explicitly opt in to re-editing, without H3."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
KEEP = [395, 373, 382, 437]
SOURCE_FRAMES = [158, 158, 175, 175]
FPS = 60


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def run(argv):
    result = subprocess.run(argv, capture_output=True, timeout=300)
    if result.returncode:
        raise ValueError('Media command failed; inspect the local input and installed FFmpeg.')
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def filter_graph():
    parts = [f'[{i}:v]fps=60,trim=start_frame=0:end_frame={n},setpts=PTS-STARTPTS[v{i}]' for i,n in enumerate(KEEP)]
    parts += ['[v0][v1][v2][v3]concat=n=4:v=1:a=0,setsar=1[v]',
              '[4:a:0]atrim=start=0:end=26.45,asetpts=PTS-STARTPTS,afade=t=out:st=25.95:d=0.5[a]']
    return ';'.join(parts)


def validate(music=None):
    folder = ROOT/'assets/default'
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    records = {entry['path']: entry for entry in manifest['assets']}
    clips = [folder/f'clips/part-{i:02d}.mp4' for i in range(1,5)]
    for clip,frames in zip(clips,SOURCE_FRAMES):
        entry = records[clip.relative_to(folder).as_posix()]
        if sha(clip) != entry['sha256']:
            raise ValueError('Default clip hash mismatch; do not use this timing on different source frames.')
        videos = [s for s in probe(clip)['streams'] if s['codec_type']=='video']
        if len(videos)!=1:
            raise ValueError('Expected one video stream.')
        v=videos[0]
        if (int(v['nb_read_frames']),v['width'],v['height'],Fraction(v['avg_frame_rate'])) != (frames,1344,768,Fraction(24)):
            raise ValueError('Default clip geometry, FPS or frame count differs from this preset.')
    selected_music = Path(music).resolve() if music else folder/'music.m4a'
    if not music and sha(selected_music)!=records['music.m4a']['sha256']:
        raise ValueError('Default music hash mismatch.')
    audio=[s for s in probe(selected_music)['streams'] if s['codec_type']=='audio']
    if len(audio)!=1 or float(audio[0].get('duration',0))<26.45:
        raise ValueError('Choose a single audio track at least 26.45 seconds long; no silent padding is applied.')
    return clips,selected_music


def render(clips,music,output):
    output=Path(output).resolve()
    if output.suffix.lower()!='.mp4' or output.exists():
        raise ValueError('Choose a new .mp4 output file.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='heartache-edit-',dir=output.parent) as tmp:
        target=Path(tmp)/'render.mp4'
        command=['ffmpeg','-nostdin','-v','error','-n']
        for clip in clips: command += ['-i',str(clip)]
        command += ['-i',str(music),'-filter_complex',filter_graph(),'-map','[v]','-map','[a]',
                    '-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r','60',
                    '-c:a','aac','-b:a','320k','-ar','44100','-ac','2','-t','26.45',
                    '-map_metadata','-1','-map_metadata:s','-1','-map_chapters','-1','-movflags','+faststart',str(target)]
        run(command)
        media=probe(target)
        video=[s for s in media['streams'] if s['codec_type']=='video'][0]
        audio=[s for s in media['streams'] if s['codec_type']=='audio']
        if int(video['nb_read_frames'])!=sum(KEEP) or Fraction(video['avg_frame_rate'])!=FPS or not audio:
            raise ValueError('Rendered media does not match the timeline; no output published.')
        if abs(float(audio[0].get('duration',0))-26.45)>0.1:
            raise ValueError('Rendered audio duration differs from the timeline.')
        run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(target),'-map','0:v:0','-map','0:a:0','-f','null','-'])
        # Exclusive creation prevents overwriting another output made during rendering.
        with output.open('xb') as dest, target.open('rb') as src:
            for block in iter(lambda:src.read(1024*1024),b''):dest.write(block)
    return {'frames':1587,'fps':60,'sha256':sha(output),'visual_review':'pending','audio_review':'pending'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--music',type=Path,help='Optional replacement soundtrack; otherwise use the bundled music.')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:
        clips,music=validate(args.music)
        if args.execute:
            if not args.output:raise ValueError('--execute requires --output.')
            result=render(clips,music,args.output)
        else:
            result={'status':'checked-not-rendered','frames':sum(KEEP),'fps':FPS,'seconds':sum(KEEP)/FPS,'inference':False}
        print(json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as exc:
        print('Stopped: '+str(exc) if isinstance(exc,ValueError) else 'Stopped: check local files and FFmpeg installation.')
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
