#!/usr/bin/env python3
"""Hash-gated patches for a newly created isolated installation; read-only unless --apply."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='New installation parent containing marker, ComfyUI and .venv')
    parser.add_argument('--apply', action='store_true', help='Explicitly replace ONLY the two verified source files in this isolated tree')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    template = Path(__file__).resolve().parents[2]
    lock = json.loads((template/'references/dependencies.lock.json').read_text())
    try:
        marker = root / '.heartache-isolated-install'
        if marker.is_symlink() or not marker.is_file() or marker.read_text() != 'heartache-new-environment-v1\n':
            raise ValueError('Missing valid isolated-install marker; refusing existing/shared environment')
        motion = next(s for s in lock['sources'] if s['id']=='motion-context')['patch']
        kernel = lock['int8_patch']
        entries = [
            ('ComfyUI/custom_nodes/H3MotionContextOfficial/nodes.py', 'vendor/motion-context/patched/nodes.py', motion),
            ('.venv/lib/python3.10/site-packages/comfy_kitchen/backends/triton/quantization.py', kernel['patched_file'], kernel),
        ]
        staged, report = [], []
        for relative, vendored, hashes in entries:
            target = root / relative
            if target.is_symlink() or root not in target.resolve().parents:
                raise ValueError('Refusing symlink or path outside isolated tree: ' + relative)
            current = target.read_bytes()
            replacement = (template / vendored).read_bytes()
            if sha(replacement) != hashes['after_sha256']:
                raise ValueError('Vendored patch payload hash mismatch: ' + vendored)
            current_sha = sha(current)
            if current_sha not in (hashes['before_sha256'], hashes['after_sha256']):
                raise ValueError('Unknown source hash; no writes performed: ' + relative)
            staged.append((target, current, replacement))
            report.append({'path':relative, 'state':'already_patched' if current_sha==hashes['after_sha256'] else 'patch_available',
                           'before_sha256': current_sha, 'expected_after_sha256':hashes['after_sha256']})
        # Validate every input before making either change; preserve mode using in-place writes.
        if args.apply:
            for target, current, replacement in staged:
                if target.read_bytes() != current:
                    raise ValueError('Source changed during validation: ' + str(target))
            for target, current, replacement in staged:
                if current != replacement:
                    target.write_bytes(replacement)
                if target.read_bytes() != replacement:
                    raise ValueError('Patch readback failed: ' + str(target))
            for item in report:
                item['state'] = 'verified_patched'
        print(json.dumps({'mode':'apply' if args.apply else 'read_only', 'files':report}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'error':str(exc), 'mode':'apply' if args.apply else 'read_only'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
