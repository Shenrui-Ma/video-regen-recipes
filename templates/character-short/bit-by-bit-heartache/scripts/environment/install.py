#!/usr/bin/env python3
"""Print a Linux installation shell plan. NEVER executes, installs or starts a service."""
import argparse
import json
from pathlib import Path
import shlex


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target', required=True, type=Path, help='New, nonexistent directory on the intended Linux machine')
    p.add_argument('--python', default='python3.10', help='Linux CPython 3.10 executable (not installed by this tool)')
    a = p.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    target = a.target.expanduser().absolute()
    if target.exists() or target.is_symlink():
        p.error('--target must not exist; shared/existing environments are never installation targets')
    lock = json.loads((root / 'references/dependencies.lock.json').read_text())
    q = shlex.quote
    check = "import platform,sys; assert platform.system()=='Linux' and platform.machine()=='x86_64', 'Linux x86_64 required'; assert sys.version_info[:2]==(3,10), 'CPython 3.10 required'; assert platform.libc_ver()[0]=='glibc' and tuple(map(int,platform.libc_ver()[1].split('.')[:2]))>=(2,35), 'glibc >= 2.35 required'"
    lines = ['#!/usr/bin/env bash', 'set -euo pipefail',
             '# PLAN ONLY. Review licenses, available disk, CUDA driver and memory before running.',
             '# Do not run on macOS, shared site-packages or an existing ComfyUI.',
             'TEMPLATE=' + q(str(root)), 'DEST=' + q(str(target)),
             q(a.python) + ' -c ' + q(check),
             'test ! -e "$DEST" && test ! -L "$DEST"',
             'command -v git; command -v ffmpeg; command -v ffprobe; command -v nvidia-smi',
             'nvidia-smi', 'mkdir -- "$DEST"',
             q(a.python) + ' -c ' + q("import pathlib,sys; (pathlib.Path(sys.argv[1])/'.heartache-isolated-install').write_text('heartache-new-environment-v1\n')") + ' "$DEST"',
             q(a.python) + ' -m venv "$DEST/.venv"']
    for source in lock['sources']:
        path = '$DEST/' + source['target']
        lines.extend(['git clone --no-checkout ' + q(source['repository']) + ' "' + path + '"',
                      '(cd "' + path + '" && git checkout --detach ' + q(source['revision']) + ')'])
    lines.extend([
        '"$DEST/.venv/bin/python" -m pip install --only-binary=:all: --no-deps --require-hashes -r "$TEMPLATE/vendor/python/requirements-direct-linux-py310.lock.txt"',
        '"$DEST/.venv/bin/python" -m pip check',
        '"$DEST/.venv/bin/python" "$TEMPLATE/scripts/environment/apply_patches.py" --root "$DEST" --apply',
        '"$DEST/.venv/bin/python" "$TEMPLATE/scripts/environment/apply_patches.py" --root "$DEST"',
        '# Install complete only if every command above succeeds; no models downloaded or service started.',
        '# Next: references/install.md, then model download with explicit license acceptance.',
        '# Before launch verify nvidia-smi driver/memory and choose an unused loopback port.',
        '# Normal node loading; no private Sage node and no custom-node whitelist.',
        '# Optional explicit launch (NOT executed by this plan):',
        '# cd "$DEST/ComfyUI" && "$DEST/.venv/bin/python" main.py --listen 127.0.0.1 --port 8188',
    ])
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
