#!/usr/bin/env python3
"""Print hash-verified H3 model download commands; never download or write files."""
import argparse
import json
from pathlib import Path
import shlex


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--comfy-root', required=True, type=Path, help='Intended ComfyUI root for the printed shell plan')
    a = p.parse_args(argv)
    template = Path(__file__).resolve().parents[2]
    lock = json.loads((template/'references/dependencies.lock.json').read_text())
    q = shlex.quote
    lines = ['#!/usr/bin/env bash', 'set -euo pipefail',
             '# Review vendor/model-licenses/MiniMax-H3-LICENSE including territory and commercial restrictions.',
             'test "${I_ACCEPT_MINIMAX_H3_LICENSE:-}" = yes || { printf "%s\\n" "Read the license, then explicitly set I_ACCEPT_MINIMAX_H3_LICENSE=yes" >&2; exit 2; }',
             'command -v curl; command -v python3']
    verify = "import hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); assert p.stat().st_size==int(sys.argv[2]), 'size mismatch: '+str(p); h=hashlib.sha256(); f=p.open('rb'); [h.update(b) for b in iter(lambda:f.read(8*1024*1024),b'')]; f.close(); assert h.hexdigest()==sys.argv[3], 'SHA-256 mismatch: '+str(p); print('verified',p)"
    for model in lock['models']:
        target = a.comfy_root.expanduser().absolute()/model['target']
        part = Path(str(target)+'.part')
        def check(path):
            return 'python3 -c ' + q(verify) + ' ' + q(str(path)) + ' ' + str(model['bytes']) + ' ' + q(model['sha256'])
        lines += ['# '+model['filename'], 'if test -f '+q(str(target))+'; then',
                  '  '+check(target), 'else', '  mkdir -p -- '+q(str(target.parent)),
                  '  curl --fail --location --proto =https --retry 3 --continue-at - --output '+q(str(part))+' '+q(model['url']),
                  '  '+check(part), '  mv -n -- '+q(str(part))+' '+q(str(target)),
                  '  '+check(target), 'fi']
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
