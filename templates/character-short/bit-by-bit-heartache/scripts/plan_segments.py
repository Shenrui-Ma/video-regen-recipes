#!/usr/bin/env python3
"""Plan native H3 segments from a calibrated sample-frame capacity, without inference."""


def plan_segments(total_frames, max_sample_frames, context_frames=22):
    if any(type(v) is not int for v in (total_frames, max_sample_frames, context_frames)):
        raise ValueError('Frame counts must be integers, not booleans or fractions.')
    if total_frames < 1 or max_sample_frames < 5 or context_frames < 0:
        raise ValueError('Need positive duration, at least five sample frames and nonnegative context.')
    capacity = (max_sample_frames - 5) // 17 * 17 + 5
    if total_frames > capacity and capacity <= context_frames:
        raise ValueError('Capacity cannot hold context plus new frames; more segments will not help.')
    rows = []
    start = 0
    while start < total_frames:
        trim = context_frames if rows else 0
        visible = min(capacity - trim, total_frames - start)
        sample = max(5, ((visible + trim - 5 + 16) // 17) * 17 + 5)
        rows.append({
            'segment': len(rows) + 1,
            'predecessor': len(rows) if rows else None,
            'timeline_start': start,
            'timeline_end': start + visible,
            'visible_frames': visible,
            'sample_frames': sample,
            'head_trim_frames': trim,
            'publish_end': trim + visible,
            'unpublished_tail_frames': sample - trim - visible,
        })
        start += visible
    return rows


def hardware_report():
    import csv
    import platform
    import shutil
    import subprocess
    result = {'system': platform.system(), 'gpus': [], 'probe_status': 'nvidia-smi-unavailable'}
    executable = shutil.which('nvidia-smi')
    if not executable:
        return result
    try:
        proc = subprocess.run([executable, '--query-gpu=uuid,name,memory.total,memory.free',
                               '--format=csv,noheader,nounits'],
                              capture_output=True, text=True, timeout=10, check=True)
        for row in csv.reader(proc.stdout.splitlines()):
            uuid, name, total, free = [v.strip() for v in row]
            result['gpus'].append({'uuid': uuid, 'name': name,
                                   'total_mib': int(total), 'free_mib': int(free)})
        result['probe_status'] = 'ok'
    except (OSError, ValueError, subprocess.SubprocessError):
        result['gpus'] = []
        result['probe_status'] = 'probe-failed'
    return result


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames', type=int, required=True, help='Target visible frames, not historical sample sum')
    parser.add_argument('--max-sample-frames', type=int, required=True,
                        help='Agent-selected capacity including context, based on hardware and calibration')
    parser.add_argument('--context-frames', type=int, default=22)
    args = parser.parse_args()
    try:
        rows = plan_segments(args.frames, args.max_sample_frames, args.context_frames)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({'schema_version': 1, 'hardware': hardware_report(),
                      'capacity_basis': 'agent-supplied; calibration-required',
                      'inference_verified': False, 'segment_count': len(rows),
                      'segments': rows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
