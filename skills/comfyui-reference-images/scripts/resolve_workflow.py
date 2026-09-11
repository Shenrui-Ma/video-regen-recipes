#!/usr/bin/env python3
"""Resolve a catalog workflow from a local toolkit or its pinned public revision."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import urllib.request

LOCK=Path(__file__).resolve().parents[1]/'references/toolkit.lock.json'


def checked(data,entry):
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:
        raise ValueError('Workflow checksum differs from the pinned catalog.')
    graph=json.loads(data)
    if not isinstance(graph,dict) or not graph or not all(isinstance(n,dict) and 'class_type' in n and 'inputs' in n for n in graph.values()):
        raise ValueError('Artifact is not a ComfyUI API template.')
    return data


def resolve(workflow_id,output,toolkit_dir=None,offline=False):
    lock=json.loads(LOCK.read_text(encoding='utf-8'))
    matches=[item for item in lock['workflows'] if item['id']==workflow_id]
    if len(matches)!=1:raise ValueError('Workflow ID is not present in the pinned catalog.')
    entry=matches[0];relative=PurePosixPath(entry['path'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid catalog path.')
    output=Path(output)
    if output.exists():
        checked(output.read_bytes(),entry)
        return {'status':'reused','workflow':workflow_id,'revision':lock['revision']}
    if toolkit_dir:
        root=Path(toolkit_dir).resolve();source=(root/relative).resolve()
        if not source.is_relative_to(root):raise ValueError('Artifact is outside the toolkit checkout.')
        data=source.read_bytes()
    else:
        if offline:raise ValueError('Offline mode needs a verified cache file or a toolkit checkout.')
        if lock['repository']!='https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit' or not re.fullmatch('[0-9a-f]{40}',lock['revision']):
            raise ValueError('Unexpected toolkit repository or revision.')
        url='https://raw.githubusercontent.com/Shenrui-Ma/shenrui-comfyui-toolkit/'+lock['revision']+'/'+relative.as_posix()
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(2*1024*1024+1)
    if len(data)>2*1024*1024:raise ValueError('Workflow exceeds the artifact size limit.')
    checked(data,entry)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(data)
    return {'status':'resolved','workflow':workflow_id,'revision':lock['revision'],'sha256':entry['sha256']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflow_id');parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--toolkit-dir',type=Path,default=os.environ.get('COMFYUI_TOOLKIT_DIR'))
    parser.add_argument('--offline',action='store_true');args=parser.parse_args()
    try:print(json.dumps(resolve(args.workflow_id,args.output,args.toolkit_dir,args.offline)))
    except (OSError,ValueError,KeyError):
        print('Stopped: verify the workflow ID, toolkit version, cache and network access. No workflow executed.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
