#!/usr/bin/env python3
"""Build and verify a text-only Skill ZIP; --full explicitly includes local binaries."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

TEMPLATE=Path(__file__).resolve().parents[2]
TEXT_SUFFIXES={'.py','.md','.json','.txt','.yaml','.yml','.toml','.sh','.ps1','.patch','.rst','.csv','.ini','.cfg','.lock'}
TEXT_NAMES={'LICENSE','NOTICE','COPYING','Makefile','Dockerfile','.gitignore','.gitattributes'}
PRIVATE_PATTERN=re.compile(r'/(?:Users|home|data\d+)/[A-Za-z][\w.-]+|CASIA_[A-Z0-9]+|telegram\.org/bot\d+:[A-Za-z0-9_-]+|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def package(root,target,portable=True):
    root=Path(root).resolve(); target=Path(target).resolve()
    if target.exists(): raise FileExistsError(str(target))
    if target.is_relative_to(root): raise ValueError('Write archive outside the source template')
    entries=[]; omitted=[]
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        if any(x in {'.git','__pycache__','.pytest_cache','.venv','.test-venv','venv','work','outputs','dist','h3-local'} for x in rel.parts) or p.suffix in {'.pyc','.zip','.part','.log'}: continue
        if p.name == 'handoff.json': continue
        if p.is_symlink(): raise ValueError('Symlink in template: '+str(rel))
        if not p.is_file(): continue
        if p.name=='.env' or p.suffix in {'.pem','.key'}: raise ValueError('Credential file forbidden')
        is_text=p.suffix.lower() in TEXT_SUFFIXES or p.name in TEXT_NAMES or p.name.endswith(('-LICENSE','-NOTICE'))
        if is_text:
            text=p.read_text(encoding='utf-8')
            is_text='\0' not in text
            if PRIVATE_PATTERN.search(text):
                raise ValueError('Private machine path or credential detected: '+rel.as_posix())
        row={'path':rel.as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)}
        if portable and not is_text:
            omitted.append(row)
        else: entries.append((p,row))
    if not any(row['path']=='SKILL.md' for _,row in entries): raise ValueError('Missing SKILL entry point')
    manifest={'schema_version':1,'mode':'portable' if portable else 'full','files':[row for _,row in entries],
              'omitted_downloadable_assets':omitted,
              'acquire_runtime_assets':'python scripts/distribution/fetch_assets.py',
              'asset_manifest':'assets/runtime-assets.json',
              'portable_policy':'Text allowlist only; all media, weights and unknown binary formats are omitted everywhere. Local source files are unchanged. Not every omitted file is a downloadable runtime asset; consult the asset and model manifests.',
              'large_model_policy':'Models stay external; pinned sources and placement in references/dependencies.lock.json',
              'verification_scope':'Byte integrity and offline package checks; not fresh GPU inference'}
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,row in entries: z.write(p,row['path'])
        z.writestr('BUNDLE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        z.writestr('START-HERE.txt','Read SKILL.md then README.md and assets/README.md. The default portable archive is text-only: documentation, scripts, workflows and manifests; no images, audio, video or model weights. Run python scripts/distribution/fetch_assets.py for hash-pinned runtime inputs. Optional historical assets require explicit selection. --full includes existing local binaries and is not lightweight. Model download and setup are explicit separate steps. Never treat historical clips as a newly generated character.\n')
    verified=verify_archive(target)
    return {'archive':str(target),'bytes':target.stat().st_size,'sha256':sha(target),'included_files':len(entries),
            'omitted_files':len(omitted),'verified':verified['verified']}

def verify_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)): raise ValueError('Duplicate ZIP entry')
        for name in names:
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name: raise ValueError('Unsafe ZIP entry')
        manifest=json.loads(z.read('BUNDLE-MANIFEST.json'))
        expected={r['path'] for r in manifest['files']}|{'BUNDLE-MANIFEST.json','START-HERE.txt'}
        if set(names)!=expected: raise ValueError('ZIP inventory mismatch')
        for row in manifest['files']:
            h=hashlib.sha256(); size=0
            with z.open(row['path']) as f:
                while b:=f.read(1024*1024): h.update(b); size+=len(b)
            if h.hexdigest()!=row['sha256'] or size!=row['bytes']: raise ValueError('ZIP hash/size mismatch')
        return {'verified':True,'included_files':len(manifest['files']),'omitted_files':len(manifest['omitted_downloadable_assets'])}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=TEMPLATE)
    p.add_argument('--output',type=Path)
    p.add_argument('--full',action='store_true',help='Include existing local binaries (not lightweight); downloads nothing')
    p.add_argument('--verify',type=Path)
    a=p.parse_args()
    if a.verify: result=verify_archive(a.verify)
    else:
        if a.output is None: p.error('--output is required')
        result=package(a.root,a.output,portable=not a.full)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
