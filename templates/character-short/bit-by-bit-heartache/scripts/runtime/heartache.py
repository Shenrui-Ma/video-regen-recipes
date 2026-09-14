#!/usr/bin/env python3
"""Heartache portable runtime: offline prepare/smoke; run submits only with --execute."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import uuid

from graphs import (TEMPLATE, build, load, load_graph, plan_segments, to_editor,
                    from_editor, validate_graph)
from local_io import contained, copy_verified, digest, history_file, stop_gate
from media import prepare_references, probe, validate_segment_latent, verify_video, assemble, preflight_media
from run_segment import API, RunnerError, atomic_json, run as run_segment, state_lock


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def smoke(args):
    schema = read(args.object_info) if args.object_info else None
    if args.host:
        if schema is not None:
            raise ValueError('CHOOSE_HOST_OR_OBJECT_INFO')
        schema = API(args.host, args.timeout, 1).request('/object_info')
    checked = []
    for name in ('first', 'continue'):
        graph = load_graph(name)
        validate_graph(graph, schema)
        if from_editor(to_editor(graph, schema)) != graph:
            raise ValueError('EDITOR_ROUNDTRIP')
        checked.append(name)
    return {'status': 'SCHEMA_OK', 'graphs': checked,
            'schema_source': args.host or args.object_info or 'bundled node-schema.json',
            'inference': False, 'clean_install_inference_verified': False}, 0


def prepare(args):
    assets = read(TEMPLATE / 'assets/runtime-assets.json')['assets']
    def source(explicit, role):
        item = next(x for x in assets if x['role'] == role)
        path = Path(explicit).resolve() if explicit else TEMPLATE / 'assets' / item['path']
        if not path.is_file():
            raise ValueError('ASSET_MISSING: ' + str(path))
        if not explicit and digest(path) != item['sha256']:
            raise ValueError('BUNDLED_ASSET_HASH_MISMATCH: ' + role)
        return path
    driver = source(args.driver, 'motion_reference')
    music = source(args.music, 'soundtrack')
    character = source(args.character_image, 'default_character')
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError('PILLOW_REQUIRED: install Pillow in the runner environment') from exc
    with Image.open(character) as image:
        if 'A' in image.getbands() or 'transparency' in image.info:
            raise ValueError('TRANSPARENT_REFERENCE_REQUIRES_COMPOSITE: use scripts/character/prepare_character.py first, then pass its RGB character.png')
        image.verify()
    meta = probe(driver)
    if meta['width'] != 1344 or meta['height'] != 768:
        raise ValueError('DRIVER_MUST_BE_1344x768')
    rows = plan_segments(args.frames if args.frames is not None else meta['frames'], args.max_sample_frames, 22)
    if rows[-1]['timeline_end'] > meta['frames']:
        raise ValueError('DRIVER_TOO_SHORT')
    if not 0 <= args.seed < 2**64:
        raise ValueError('SEED_MUST_BE_UINT64')
    work = Path(args.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=False)
    namespace = 'heartache-' + uuid.uuid4().hex
    inputs = {}
    for role, path in [('character', character), ('music', music)]:
        relative = 'inputs/' + role + path.suffix.lower()
        sha = copy_verified(path, work / relative)
        inputs[role] = {'path': relative, 'sha256': sha}
    references = prepare_references(driver, work / 'references', rows)
    for row, reference in zip(rows, references):
        number = row['segment']
        seg = work / 'segments' / f'seg{number:02d}'
        seg.mkdir(parents=True)
        predecessor = row['predecessor']
        graph = build(row, namespace + '/' + inputs['character']['path'],
                      namespace + '/references/' + reference['file'],
                      args.character_description, args.seed,
                      video=f'{namespace}/checkpoints/seg{predecessor:02d}-video.latent' if predecessor else None,
                      audio=f'{namespace}/checkpoints/seg{predecessor:02d}-audio.latent' if predecessor else None,
                      prefix=namespace,
                      models={key: getattr(args, key) for key in ('transformer', 'text_encoder', 'video_vae', 'audio_vae') if getattr(args, key)})
        atomic_json(seg / 'graph.api.json', graph)
        atomic_json(seg / 'graph.editor.json', to_editor(graph))
        row['graph_sha256'] = digest(seg / 'graph.api.json')
    config = {'schema_version': 1, 'namespace': namespace, 'segments': rows,
              'inputs': inputs, 'references': references, 'driver_sha256': digest(driver),
              'max_sample_frames': args.max_sample_frames, 'capacity_basis': 'user-supplied; calibration-required',
              'seed': args.seed, 'inference': False}
    atomic_json(work / 'run.json', config)
    return {'status': 'PREPARED', 'work_dir': str(work), 'segment_count': len(rows),
            'visible_frames': rows[-1]['timeline_end'], 'max_sample_frames': args.max_sample_frames,
            'inference': False}, 0


def run(args):
    work = Path(args.work_dir).resolve()
    config = read(work / 'run.json')
    rows = config['segments']
    until = args.until_segment if args.until_segment is not None else len(rows)
    if not 1 <= until <= len(rows):
        raise ValueError('UNTIL_SEGMENT_OUT_OF_RANGE')
    if not args.execute:
        return {'status': 'DRY_RUN', 'segment_count': len(rows), 'until_segment': until,
                'inference': False, 'submission_requires': '--execute --comfy-root ROOT'}, 0
    if not args.comfy_root:
        raise ValueError('EXECUTION_REQUIRES_LOCAL_COMFY_ROOT')
    comfy = Path(args.comfy_root).resolve()
    if not (comfy / 'input').is_dir() or not (comfy / 'output').is_dir():
        raise ValueError('COMFY_INPUT_OUTPUT_MUST_EXIST_LOCALLY')
    stop_gate(work)
    with state_lock(work / '.runtime.lock'):
        identity = {'run_sha256': digest(work / 'run.json'), 'comfy_root': str(comfy), 'host': args.host.rstrip('/')}
        target = work / 'execution-target.json'
        if target.exists():
            if read(target) != identity:
                raise ValueError('EXECUTION_TARGET_OR_PLAN_CHANGED')
        else:
            atomic_json(target, identity)
        # Validate every prepared dependency before constructing a network client.
        for item in config['inputs'].values():
            if digest(contained(work, item['path'])) != item['sha256']:
                raise ValueError('PREPARED_INPUT_CHANGED')
        for row, ref in zip(rows, config['references']):
            seg = work / 'segments' / f"seg{row['segment']:02d}"
            if digest(seg / 'graph.api.json') != row['graph_sha256']:
                raise ValueError('PREPARED_GRAPH_CHANGED')
            if digest(contained(work / 'references', ref['file'])) != ref['sha256']:
                raise ValueError('PREPARED_REFERENCE_CHANGED')
        namespace = config['namespace']
        stage = contained(comfy / 'input', namespace)
        for item in config['inputs'].values():
            if item is config['inputs']['character']:
                copy_verified(contained(work, item['path']), contained(stage, item['path']))
        api = API(args.host, args.timeout, args.interval)
        schema = api.request('/object_info')
        for row in rows:
            validate_graph(read(work / 'segments' / f"seg{row['segment']:02d}" / 'graph.api.json'), schema)
        schema_path = work / 'execution-object-info.json'
        if not schema_path.exists():
            atomic_json(schema_path, schema)
        published = []
        for row, ref in zip(rows[:until], config['references'][:until]):
            stop_gate(work)
            number = row['segment']
            seg = work / 'segments' / f'seg{number:02d}'
            graph = read(seg / 'graph.api.json')
            job = seg / 'job'
            receipt_path = seg / 'verification.json'
            if not (job / 'state.json').exists() and (
                any((seg / name).exists() for name in
                    ('video.latent', 'audio.latent', 'published.mp4', 'verification.json'))
                or (job.exists() and any(job.iterdir()))
            ):
                raise ValueError('ORPHANED_ARTIFACTS_WITHOUT_JOB_NO_RESAMPLE')
            if receipt_path.exists():
                if not (job / 'state.json').exists():
                    raise ValueError('COMPLETED_RECEIPT_WITHOUT_JOB_NO_RESAMPLE')
                receipt = read(receipt_path)
                for name, sha in receipt['artifact_sha256'].items():
                    if digest(contained(seg, name)) != sha:
                        raise ValueError('COMPLETED_ARTIFACT_CHANGED_NO_RESAMPLE')
            copy_verified(contained(work / 'references', ref['file']), contained(stage, 'references/' + ref['file']))
            if number > 1:
                previous = work / 'segments' / f'seg{number-1:02d}'
                prior = read(previous / 'verification.json')
                prior_state = read(previous / 'job/state.json')
                if prior['row'] != rows[number - 2] or prior['prompt_id'] != prior_state['prompt_id'] or prior_state['status'] != 'SUCCESS':
                    raise ValueError('PREDECESSOR_SIDECAR_STATE_MISMATCH')
                binding = {'segment': number - 1, 'prompt_id': prior['prompt_id'],
                           'verification_sha256': digest(previous / 'verification.json'),
                           'artifact_sha256': prior['artifact_sha256']}
                binding_path = seg / 'predecessor.json'
                if binding_path.exists():
                    if read(binding_path) != binding:
                        raise ValueError('PREDECESSOR_BINDING_CHANGED_NO_RESAMPLE')
                elif (job / 'state.json').exists():
                    raise ValueError('PREDECESSOR_BINDING_MISSING_NO_RESAMPLE')
                else:
                    atomic_json(binding_path, binding)
                for part in ('video', 'audio'):
                    latent = previous / (part + '.latent')
                    if digest(latent) != binding['artifact_sha256'][part + '.latent']:
                        raise ValueError('PREDECESSOR_SHA_MISMATCH')
                    validate_segment_latent(latent, part, rows[number - 2]['sample_frames'])
                    copy_verified(latent, contained(stage, f'checkpoints/seg{number-1:02d}-{part}.latent'))
            stop_gate(work)
            if not (job / 'state.json').exists():
                preflight_media()  # Real AAC encode before any new expensive submission.
            result, code = run_segment(api, graph, job, False)
            if code:
                return {'status': result['status'], 'segment': number,
                        'prompt_id': result.get('prompt_id'), 'resample_allowed': False,
                        'recovery': 'Resume this workdir to query the original prompt; failed sampling/decode requires separate no-sampler recovery.'}, code
            if not receipt_path.exists():
                outputs = result['outputs']
                for node, part in [('61', 'video'), ('62', 'audio')]:
                    source = history_file(outputs, node, '.latent', comfy)
                    validate_segment_latent(source, part, row['sample_frames'])
                    copy_verified(source, seg / (part + '.latent'))
                source = history_file(outputs, '14', '.mp4', comfy)
                verify_video(source, row['visible_frames'])
                copy_verified(source, seg / 'published.mp4')
                receipt = {'segment': number, 'row': row, 'prompt_id': result['prompt_id'],
                           'graph_sha256': row['graph_sha256'], 'head_trim_applied_in_graph_only': row['head_trim_frames'],
                           'artifact_sha256': {name: digest(seg / name) for name in ('video.latent', 'audio.latent', 'published.mp4')}}
                atomic_json(receipt_path, receipt)
            published.append(seg / 'published.mp4')
            # Every prefix is a separate immutable assembly, always music from t=0.
            assembly_dir = work / 'assemblies' / f'through-seg{number:02d}'
            assemble(published, contained(work, config['inputs']['music']['path']), assembly_dir, rows[:number])
        return {'status': 'COMPLETE' if until == len(rows) else 'CALIBRATION_COMPLETE',
                'through_segment': until, 'segment_count': len(rows),
                'file': str(work / 'assemblies' / f'through-seg{until:02d}' / 'final.mp4'),
                'visual_alignment_verified': False, 'clean_install_inference_verified': False}, 0


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('smoke', help='Validate first/continue graphs; never submits')
    s.add_argument('--object-info')
    s.add_argument('--host', help='GET live /object_info only')
    s.add_argument('--timeout', type=float, default=30)
    q = sub.add_parser('prepare', help='Prepare immutable inputs/graphs using calibrated capacity; CPU only')
    q.add_argument('--work-dir', required=True)
    q.add_argument('--character-image')
    q.add_argument('--driver')
    q.add_argument('--music')
    q.add_argument('--character-description', default='The person shown in the supplied character reference image')
    q.add_argument('--frames', type=int)
    q.add_argument('--max-sample-frames', type=int, required=True)
    q.add_argument('--seed', type=int, default=42)
    for key in ('transformer', 'text_encoder', 'video_vae', 'audio_vae'):
        q.add_argument('--' + key.replace('_', '-'))
    r = sub.add_parser('run', help='Resume the same workdir; no failed/ambiguous job is resampled')
    r.add_argument('--work-dir', required=True)
    r.add_argument('--comfy-root')
    r.add_argument('--host', default='http://127.0.0.1:8188')
    r.add_argument('--execute', action='store_true')
    r.add_argument('--until-segment', type=int, help='Inclusive calibration stop; resume same workdir later')
    r.add_argument('--timeout', type=float, default=30)
    r.add_argument('--interval', type=float, default=10)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        for key in ('timeout', 'interval'):
            value = getattr(args, key, 1)
            if not math.isfinite(value) or value <= 0:
                raise ValueError('TIMING_MUST_BE_POSITIVE_FINITE')
        result, code = {'smoke': smoke, 'prepare': prepare, 'run': run}[args.command](args)
    except KeyboardInterrupt:
        result, code = {'status': 'INTERRUPTED_RESUME_SAME_WORKDIR'}, 130
    except (OSError, ValueError, KeyError, TypeError, RunnerError, subprocess.SubprocessError) as exc:
        result, code = {'status': 'ERROR', 'error': str(exc)}, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
