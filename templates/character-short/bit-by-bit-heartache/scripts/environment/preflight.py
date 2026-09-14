#!/usr/bin/env python3
"""Read-only H3 environment checks. No torch import, installs, or prompt POST."""
import hashlib
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_models(models, root, verify_hashes=False):
    issues = []
    for model in models:
        path = Path(root) / model['target']
        if not path.is_file():
            issues.append({'code': 'missing_model', 'path': model['target']})
        elif path.stat().st_size != model['bytes']:
            issues.append({'code': 'model_size_mismatch', 'path': model['target']})
        elif verify_hashes and digest(path) != model['sha256']:
            issues.append({'code': 'model_hash_mismatch', 'path': model['target']})
    return issues


def check_nodes(required, info, inventory=None, argv=()):
    """inventory maps package ids to installed/disabled/import_error evidence."""
    issues = []
    inventory = inventory or {}
    for node, item in required.items():
        if node in info:
            continue
        package = item['package']
        evidence = inventory.get(package, {})
        disabled = evidence.get('disabled', False)
        if package != 'comfyui' and '--disable-all-custom-nodes' in argv:
            disabled = True
            if '--whitelist-custom-nodes' in argv:
                start = list(argv).index('--whitelist-custom-nodes') + 1
                allowed = []
                for token in list(argv)[start:]:
                    if token.startswith('--'):
                        break
                    allowed.append(token)
                if 'H3MotionContextOfficial' in allowed:
                    disabled = False
        if disabled:
            code = 'node_disabled'
        elif evidence.get('import_error'):
            code = 'node_import_failed'
        elif evidence.get('installed'):
            code = 'node_installed_not_loaded'
        elif evidence.get('installed') is False:
            code = 'node_package_missing'
        else:
            code = 'node_unregistered_cause_unknown'
        issues.append({'code': code, 'node': node, 'package': package})
    return issues


def input_spec(fields, name):
    """Resolve V1 inputs and V3 dotted autogrow ports, including nested template."""
    import re
    if name in fields:
        return fields[name]
    if '.' not in name:
        return None
    group, leaf = name.split('.', 1)
    parent = fields.get(group)
    if not parent or parent[0] != 'COMFY_AUTOGROW_V3':
        return None
    template = parent[1].get('template', parent[1])
    match = re.fullmatch(re.escape(template.get('prefix', '')) + r'(\d+)', leaf)
    if not match or not 0 <= int(match[1]) < template.get('max', 0):
        return None
    children = template.get('input', {}).get('required', {})
    return next(iter(children.values())) if len(children) == 1 else None


def check_graph(graph, info):
    issues = []
    if not isinstance(graph, dict) or not graph or 'nodes' in graph:
        return [{'code': 'invalid_api_graph'}]
    edges = {}
    for node_id, node in graph.items():
        if not isinstance(node, dict) or 'class_type' not in node:
            issues.append({'code': 'invalid_api_node', 'node': node_id})
            continue
        cls = node['class_type']
        if cls not in info:
            issues.append({'code': 'node_unregistered', 'node': node_id, 'class_type': cls})
            continue
        spec = info[cls]
        required = dict(spec.get('input', {}).get('required', {}))
        fields = {**required, **spec.get('input', {}).get('optional', {})}
        inputs = node.get('inputs', {})
        # Dynamic combo branches flatten into dotted API ports, recursively.
        todo = list(fields.items())
        while todo:
            parent_name, parent_spec = todo.pop()
            if parent_spec[0] != 'COMFY_DYNAMICCOMBO_V3':
                continue
            for option in parent_spec[1].get('options', []):
                if not isinstance(option, dict) or option.get('key') != inputs.get(parent_name):
                    continue
                for category in ('required', 'optional'):
                    for leaf, child in option.get('inputs', {}).get(category, {}).items():
                        dotted = parent_name + '.' + leaf
                        fields[dotted] = child
                        if category == 'required':
                            required[dotted] = child
                        todo.append((dotted, child))
        edges[node_id] = []
        for name, val in required.items():
            if name not in inputs and val[0] != 'COMFY_AUTOGROW_V3':
                issues.append({'code': 'required_input_missing', 'node': node_id, 'input': name})
        for name, value in inputs.items():
            expected = input_spec(fields, name)
            location = {'node': node_id, 'input': name}
            if expected is None:
                issues.append({'code': 'unknown_input', **location})
                continue
            kind = expected[0]
            opts = expected[1] if len(expected) > 1 and isinstance(expected[1], dict) else {}
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int):
                source, slot = value
                edges[node_id].append(source)
                source_spec = info.get(graph.get(source, {}).get('class_type'), {})
                outputs = source_spec.get('output', [])
                if source not in graph:
                    issues.append({'code': 'link_source_missing', **location})
                elif not 0 <= slot < len(outputs):
                    issues.append({'code': 'link_output_slot_mismatch', **location})
                elif isinstance(kind, str) and kind not in ('*', 'COMBO') and outputs[slot] not in (kind, '*'):
                    issues.append({'code': 'link_type_mismatch', **location})
                continue
            enum = kind if isinstance(kind, list) else opts.get('options')
            if kind == 'COMFY_DYNAMICCOMBO_V3' and enum is not None:
                enum = [option['key'] for option in enum]
            if enum is not None and value not in enum:
                if (cls, name) in (('UNETLoader', 'unet_name'), ('CLIPLoader', 'clip_name'), ('VAELoader', 'vae_name')):
                    code = 'model_not_enumerated'
                elif cls in ('LoadImage', 'LoadVideo', 'LoadLatent'):
                    code = 'input_not_staged'
                else:
                    code = 'enum_value_mismatch'
                issues.append({'code': code, **location})
            elif kind in ('INT', 'FLOAT'):
                valid = isinstance(value, int) if kind == 'INT' else isinstance(value, (int, float))
                if not valid or isinstance(value, bool):
                    issues.append({'code': 'input_type_mismatch', **location})
                elif value < opts.get('min', float('-inf')) or value > opts.get('max', float('inf')):
                    issues.append({'code': 'input_range_mismatch', **location})
            elif kind == 'BOOLEAN' and not isinstance(value, bool):
                issues.append({'code': 'input_type_mismatch', **location})
            elif kind == 'STRING' and not isinstance(value, str):
                issues.append({'code': 'input_type_mismatch', **location})
            elif isinstance(kind, str) and kind not in ('STRING', 'BOOLEAN', 'INT', 'FLOAT', 'COMBO', 'COMFY_DYNAMICCOMBO_V3') and not opts.get('default'):
                issues.append({'code': 'input_requires_link', **location})
    visited, active = set(), set()
    def cyclic(node):
        if node in active:
            return True
        if node in visited:
            return False
        active.add(node)
        for source in edges.get(node, []):
            if cyclic(source):
                return True
        active.remove(node)
        visited.add(node)
        return False
    if any(cyclic(node) for node in edges):
        issues.append({'code': 'graph_cycle'})
    return issues


def main(argv=None):
    import argparse
    import importlib.metadata
    import json
    import platform
    import shutil
    import sys
    import urllib.request
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy-root', type=Path, help='Existing ComfyUI root; only read files, never modify')
    parser.add_argument('--python-site', type=Path, help='Existing isolated site-packages; read metadata and INT8 source only')
    parser.add_argument('--url', help='Existing service base URL; GET /object_info and /system_stats only')
    parser.add_argument('--object-info', type=Path, help='Offline object_info JSON, instead of a service')
    parser.add_argument('--inventory', type=Path, help='Optional package installed/disabled/import_error JSON')
    parser.add_argument('--verify-model-hashes', action='store_true', help='Read all 42GB of model bytes to verify SHA-256')
    parser.add_argument('--platform', help='Explicit target OS override for planning only, not hardware validation')
    parser.add_argument('--architecture', help='Explicit target architecture override for planning only')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    lock = json.loads((root / 'references/dependencies.lock.json').read_text())
    issues, pending, methods = [], [], []
    system = {'platform': platform.system(), 'architecture': platform.machine(),
              'python': platform.python_version(), 'libc': list(platform.libc_ver())}
    target_os = args.platform or system['platform']
    target_arch = args.architecture or system['architecture']
    if target_os != 'Linux' or target_arch != 'x86_64':
        issues.append({'code': 'unsupported_platform', 'os': target_os, 'architecture': target_arch,
                       'reason': 'Pinned CPython 3.10 Linux x86_64 CUDA/Triton wheels; no macOS/MPS, Windows, ROCm or ARM recipe.'})
    if args.platform or args.architecture:
        pending.append('Explicit platform override is a plan, not observed target hardware.')
    if system['platform'] == 'Linux':
        libc, version = system['libc']
        if libc != 'glibc' or tuple(int(v) for v in version.split('.')[:2]) < (2, 35):
            issues.append({'code': 'unsupported_glibc', 'observed': system['libc'], 'required': 'glibc>=2.35'})
    for name, expected in lock['vendored_files_sha256'].items():
        path = root / name
        if not path.is_file() or digest(path) != expected:
            issues.append({'code': 'vendor_hash_mismatch', 'path': name})
    info = json.loads((root / lock['contract']).read_text())
    info_origin = 'bundled_contract_not_live'
    stats = {}
    if args.object_info:
        info = json.loads(args.object_info.read_text())
        info_origin = 'offline_snapshot_not_live'
    if args.url:
        from urllib.parse import urlsplit
        parsed = urlsplit(args.url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
            parser.error('--url must be an HTTP(S) base without credentials/query/fragment')
        try:
            for endpoint in ('object_info', 'system_stats'):
                request = urllib.request.Request(args.url.rstrip('/') + '/' + endpoint, method='GET')
                methods.append('GET /' + endpoint)
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.load(response)
                if endpoint == 'object_info':
                    info, info_origin = payload, 'live_GET'
                else:
                    stats = payload
        except Exception as exc:
            issues.append({'code': 'service_read_failed', 'detail': str(exc)})
    inventory = json.loads(args.inventory.read_text()) if args.inventory else {}
    if args.comfy_root:
        for source in lock['sources']:
            relative = Path(source['target']).relative_to('ComfyUI')
            folder = args.comfy_root / relative
            inventory.setdefault(source['id'], {'installed': folder.is_dir()})
            for name, expected in source['file_sha256'].items():
                file = folder / name
                if not file.is_file() or digest(file) != expected:
                    issues.append({'code': 'source_hash_mismatch', 'package': source['id'], 'path': name})
        issues.extend(check_models(lock['models'], args.comfy_root, args.verify_model_hashes))
        if not args.verify_model_hashes:
            pending.append('Model SHA-256 not checked; filenames/size are insufficient for byte identity.')
    else:
        pending.append('No --comfy-root: installed source hashes and model bytes not inspected.')
    if args.python_site:
        installed = {d.metadata['Name'].lower().replace('_', '-'): d.version
                     for d in importlib.metadata.distributions(path=[str(args.python_site)])}
        for package in lock['python_packages']:
            if installed.get(package['name']) != package['version']:
                issues.append({'code': 'python_package_version_mismatch', 'package': package['name'],
                               'expected': package['version'], 'actual': installed.get(package['name'])})
        kitchen = args.python_site / 'comfy_kitchen/backends/triton/quantization.py'
        expected = lock.get('int8_patch', {}).get('after_sha256')
        if not kitchen.is_file() or digest(kitchen) != expected:
            issues.append({'code': 'int8_patch_missing_or_mismatched'})
    else:
        pending.append('No --python-site: target Python package versions and installed INT8 fix unverified.')
    for tool in ('git', 'ffmpeg', 'ffprobe'):
        if not shutil.which(tool):
            issues.append({'code': 'system_tool_missing', 'tool': tool})
    argv_live = stats.get('system', {}).get('argv', [])
    issues.extend(check_nodes(lock['nodes'], info, inventory, argv_live))
    graph_results = {}
    for name in ('first', 'continue'):
        graph = json.loads((root / 'workflows' / (name + '.api.json')).read_text())
        graph_issues = check_graph(graph, info)
        graph_results[name] = graph_issues
        for issue in graph_issues:
            if issue['code'] == 'input_not_staged':
                pending.append(name + ': template placeholder not staged: ' + issue['node'] + '/' + issue['input'])
            else:
                issues.append({'workflow': name, **issue})
    if info_origin != 'live_GET':
        pending.append('Bundled/offline schema cannot establish live node registration or model enumeration.')
    pending.append('GPU memory/RAM capacity, fresh Linux installation and inference not tested by this read-only command.')
    report = {'schema_version': 1, 'mode': 'read_only', 'network_methods': methods,
              'host': system, 'target': {'os': target_os, 'architecture': target_arch},
              'schema_origin': info_origin, 'required_node_count': len(lock['nodes']),
              'graphs': graph_results, 'issues': issues, 'pending': pending,
              'static_checks_pass': not issues, 'ready_for_inference': False,
              'no_inference_performed': True,
              'service_summary': {'system': {k: v for k, v in stats.get('system', {}).items()
                                             if k in ('os', 'python_version', 'pytorch_version', 'comfyui_version')},
                                  'devices': stats.get('devices', [])}}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())

