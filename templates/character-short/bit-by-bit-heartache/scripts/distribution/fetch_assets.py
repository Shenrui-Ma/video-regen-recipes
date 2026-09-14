#!/usr/bin/env python3
"""Acquire pinned runtime assets; no model installation or inference."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import urllib.parse
import urllib.request

TEMPLATE=Path(__file__).resolve().parents[2]

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def validate(root,row):
    name=PurePosixPath(row['path']); url=urllib.parse.urlsplit(row['url'])
    if name.is_absolute() or '..' in name.parts or '\\' in row['path'] or not name.parts:
        raise ValueError('Unsafe asset path')
    if url.scheme!='https' or not url.netloc or url.username or url.password:
        raise ValueError('Asset URL must be HTTPS without credentials')
    if not re.fullmatch(r'[0-9a-f]{64}',row['sha256']) or type(row['bytes']) is not int or row['bytes']<=0:
        raise ValueError('Invalid size or SHA256')
    root=Path(root).resolve(); target=root.joinpath(*name.parts)
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Asset path escapes its root or is a symlink')
    return target

def check(root,row):
    target=validate(root,row)
    return target.is_file() and target.stat().st_size==row['bytes'] and digest(target)==row['sha256']

def acquire(root,row,cache=None):
    target=validate(root,row)
    if target.exists():
        if not check(root,row): raise ValueError('Existing asset differs; refusing overwrite: '+row['path'])
        return {'path':row['path'],'status':'already_verified','sha256':row['sha256']}
    source=Path(cache)/target.name if cache else None
    if source and source.exists():
        if source.stat().st_size!=row['bytes'] or digest(source)!=row['sha256']:
            raise ValueError('Cache asset hash mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    part=target.with_name(target.name+'.part')
    if part.is_symlink(): raise ValueError('Refusing symlink partial')
    if not part.exists():
        with part.open('xb') as out:
            if source and source.is_file():
                with source.open('rb') as f: shutil.copyfileobj(f,out,1024*1024)
            else:
                with urllib.request.urlopen(row['url'],timeout=60) as f:
                    size=0
                    while chunk:=f.read(1024*1024):
                        size+=len(chunk)
                        if size>row['bytes']: raise ValueError('Asset exceeds manifest size')
                        out.write(chunk)
            out.flush(); os.fsync(out.fileno())
    if part.stat().st_size!=row['bytes'] or digest(part)!=row['sha256']:
        raise ValueError('Partial download is incomplete or changed; inspect/remove only the .part and retry')
    os.link(part,target); part.unlink()
    if not check(root,row): raise ValueError('Published asset readback failed')
    return {'path':row['path'],'status':'copied_verified_cache' if source and source.is_file() else 'downloaded_verified','sha256':row['sha256']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asset-root',type=Path,default=TEMPLATE/'assets')
    p.add_argument('--manifest',type=Path,default=TEMPLATE/'assets/runtime-assets.json')
    p.add_argument('--cache-dir',type=Path)
    p.add_argument('--check',action='store_true',help='Read only; do not create files or use network')
    p.add_argument('--assets',nargs='+',metavar='PATH',help='Fetch/check only these manifest paths, including optional assets; paths are relative to assets/')
    p.add_argument('--without-default-character',action='store_true',help='Exclude the historical character image (already excluded by default)')
    a=p.parse_args(); rows=json.loads(a.manifest.read_text(encoding='utf-8'))['assets']
    if a.assets:
        unknown=set(a.assets)-{r['path'] for r in rows}
        if unknown: p.error('Unknown asset path: '+', '.join(sorted(unknown)))
        rows=[r for r in rows if r['path'] in a.assets]
    else:
        rows=[r for r in rows if r.get('download_by_default',r['role']!='default_character')]
    if a.without_default_character: rows=[r for r in rows if r['role']!='default_character']
    if a.check:
        statuses=[{'path':r['path'],'verified':check(a.asset_root,r)} for r in rows]
        ok=all(r['verified'] for r in statuses)
        print(json.dumps({'ok':ok,'read_only':True,'assets':statuses},indent=2)); return 0 if ok else 2
    statuses=[acquire(a.asset_root,r,a.cache_dir) for r in rows]
    print(json.dumps({'ok':True,'assets':statuses},indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
