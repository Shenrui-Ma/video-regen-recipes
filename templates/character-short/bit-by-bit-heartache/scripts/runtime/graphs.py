"""Portable bindings and LiteGraph editor export for the Core AV continuation pattern.

The graphs are not maintained here. They live in the companion toolkit repository
as parameterized templates; references/workflow.lock.json pins the commit and the
per-file SHA-256, and this module fetches, verifies and caches them before binding
the template's {{name}} placeholders.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

TEMPLATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TEMPLATE / 'scripts'))
from plan_segments import plan_segments

GRAPH_CACHE = TEMPLATE / 'workflows' / '_toolkit_graphs'
TOKEN = re.compile(r'\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}')


def load(name):
    """Load a bundled local artifact (the node schema); graphs come from the lock."""
    return json.loads((TEMPLATE / 'workflows' / name).read_text(encoding='utf-8'))


def toolkit_lock():
    return json.loads((TEMPLATE / 'references/workflow.lock.json').read_text(encoding='utf-8'))


def load_graph(name, cache_dir=None):
    """Return the pinned parameterized graph, fetching and verifying it on a cache miss."""
    lock = toolkit_lock()
    entry = next((row for row in lock['graphs'] if row['name'] == name), None)
    if entry is None:
        raise ValueError('GRAPH_NOT_PINNED: ' + name)
    cache = Path(cache_dir) if cache_dir else GRAPH_CACHE
    target = cache / entry['path'].split('/')[-1]
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256']:
        return json.loads(target.read_text(encoding='utf-8'))
    with urllib.request.urlopen(entry['url'], timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise ValueError('GRAPH_HASH_MISMATCH: ' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return json.loads(data.decode('utf-8'))


def bind(graph, values):
    """Replace whole-value {{name}} placeholders with typed values; never interpolate."""
    def walk(value):
        if isinstance(value, str):
            match = TOKEN.fullmatch(value)
            if match:
                if match.group(1) not in values:
                    raise ValueError('MISSING_BINDING: ' + match.group(1))
                return values[match.group(1)]
            if '{{' in value or '}}' in value:
                raise ValueError('UNBOUND_PLACEHOLDER')
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value
    return walk(graph)


def build(row, character, reference, description, seed, video=None, audio=None,
          prefix='heartache', models=None, cache_dir=None):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('SEED_MUST_BE_UINT64')
    if row['sample_frames'] < 5 or row['sample_frames'] % 17 != 5:
        raise ValueError('FRAME_GRID')
    if row['visible_frames'] < 1 or row['publish_end'] != row['head_trim_frames'] + row['visible_frames'] or row['publish_end'] > row['sample_frames']:
        raise ValueError('PUBLISH_RANGE')
    continuation = row['predecessor'] is not None
    template = load_graph('continue' if continuation else 'first', cache_dir)
    text = (TEMPLATE / 'prompts/ref2va.template.txt').read_text(encoding='utf-8')
    replacements = {
        'CHARACTER_DESCRIPTION': description,
        'FIXED_OUTFIT': 'the outfit and accessories shown in the character reference image',
        'VISIBLE_FRAMES': str(row['visible_frames']),
        'BACKGROUND_ANCHORS': 'the reference background structures, floor, lighting and stationary objects',
        'CURRENT_SEGMENT_ACTION_AND_CAMERA': 'Follow the current reference clip in chronological order, replacing only the main performer',
    }
    for key, value in replacements.items():
        text = text.replace('{{' + key + '}}', value)
    if '{{' in text or '}}' in text:
        raise ValueError('UNBOUND_PROMPT')
    # 模型名是模板参数：这里是本模板用的默认值，调用方可用 models={...} 覆盖。
    values = {
        'diffusion_model': 'minimax_h3_ref2va_pruned_int8_convrot.safetensors',
        'text_encoder': 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
        'video_vae': 'minimax_h3_video_vae_fp16.safetensors',
        'audio_vae': 'minimax_h3_audio_vae_fp32.safetensors',
        'prompt': text,
        'width': 1344,
        'height': 768,
        'sample_frames': row['sample_frames'],
        'seed': seed,
        'steps': 20,
        'video_prefix': f"{prefix}/seg{row['segment']:02d}-silent",
        'video_latent_prefix': f"{prefix}/seg{row['segment']:02d}-video",
        'audio_latent_prefix': f"{prefix}/seg{row['segment']:02d}-audio",
        'reference_image': character,
        'reference_video': reference,
        'visible_frames': row['visible_frames'],
    }
    model_fields = {'transformer': 'diffusion_model', 'text_encoder': 'text_encoder',
                    'video_vae': 'video_vae', 'audio_vae': 'audio_vae'}
    for key, value in (models or {}).items():
        values[model_fields[key]] = value
    if continuation:
        if not video or not audio or str(row['head_trim_frames']) not in ('5', '22', '39', '56'):
            raise ValueError('CONTINUATION_REQUIRES_BOTH_PARTS_AND_SUPPORTED_CONTEXT')
        values.update({'previous_video_latent': video, 'previous_audio_latent': audio,
                       'context_length': str(row['head_trim_frames']),
                       'audio_context_length': 24})
    elif row['head_trim_frames'] != 0:
        raise ValueError('FIRST_HAS_CONTEXT')
    g = bind(template, values)
    validate_graph(g)
    return g


def input_spec(schema, name):
    for group in ('required', 'optional'):
        fields = schema.get('input', {}).get(group, {})
        if name in fields:
            return fields[name]
        if '.' in name:
            parent, child = name.split('.', 1)
            if parent in fields and fields[parent][0] == 'COMFY_AUTOGROW_V3':
                template = fields[parent][1]['template']
                prefix = template['prefix']
                if child.startswith(prefix) and child[len(prefix):].isdigit() and int(child[len(prefix):]) < template['max']:
                    return next(iter(template['input']['required'].values()))
    raise ValueError('UNKNOWN_INPUT: ' + name)


def port_type(spec):
    return 'COMBO' if isinstance(spec[0], list) else spec[0]


def validate_graph(graph, schema=None):
    schema = schema or load('node-schema.json')
    visiting, visited = set(), set()
    def visit(node_id):
        if node_id in visiting:
            raise ValueError('GRAPH_CYCLE')
        if node_id in visited:
            return
        visiting.add(node_id)
        node = graph[node_id]
        if node['class_type'] not in schema:
            raise ValueError('MISSING_NODE_CLASS: ' + node['class_type'])
        definition = schema[node['class_type']]
        missing = set(definition['input'].get('required', {})) - set(node['inputs'])
        if missing:
            raise ValueError('MISSING_REQUIRED_INPUT: ' + ','.join(sorted(missing)))
        for name, value in node['inputs'].items():
            spec = input_spec(definition, name)
            if isinstance(value, list):
                source, slot = value
                if source not in graph or type(slot) is not int:
                    raise ValueError('BROKEN_LINK')
                outputs = schema[graph[source]['class_type']]['output']
                if slot < 0 or slot >= len(outputs) or outputs[slot] != port_type(spec):
                    raise ValueError('PORT_TYPE_MISMATCH')
                visit(source)
        visiting.remove(node_id)
        visited.add(node_id)
    for key in graph:
        visit(key)
    if schema['SaveLatent']['output'] != ['LATENT']:
        raise ValueError('CORE_SAVE_LATENT_OUTPUT_REQUIRED')
    if '53' in graph and schema['MiniMaxH3MotionContext']['output'] != ['CONDITIONING', 'INT']:
        raise ValueError('MOTION_CONTEXT_TRIM_SCHEMA_CHANGED')
    return True


def to_editor(graph, schema=None):
    """Actual links and widgets, including converted INT and V3 autogrow ports.

    Runtime property maps retain API widget names for lossless offline roundtrip;
    the editor uses the normal widgets_values/inputs/outputs fields.
    """
    schema = schema or load('node-schema.json')
    validate_graph(graph, schema)
    nodes, by_id, links = [], {}, []
    for order, (key, node) in enumerate(graph.items()):
        definition = schema[node['class_type']]
        entry = {'id': int(key), 'type': node['class_type'], 'pos': [(order % 5) * 370, (order // 5) * 370],
                 'size': [340, 290], 'flags': {}, 'order': order, 'mode': 0, 'inputs': [],
                 'outputs': [{'name': name, 'type': kind, 'links': [], 'slot_index': slot}
                             for slot, (name, kind) in enumerate(zip(definition['output_name'], definition['output']))],
                 'properties': {'Node name for S&R': node['class_type'], 'runtime_widget_names': []}, 'widgets_values': []}
        for name, value in node['inputs'].items():
            spec = input_spec(definition, name)
            kind = port_type(spec)
            widget = kind in ('STRING', 'INT', 'FLOAT', 'BOOLEAN', 'COMBO')
            if isinstance(value, list):
                inp = {'name': name, 'type': kind, 'link': None}
                if widget:
                    inp['widget'] = {'name': name}
                    entry['properties']['runtime_widget_names'].append(name)
                    entry['widgets_values'].append(spec[1].get('default', 0) if len(spec) > 1 else 0)
                entry['inputs'].append(inp)
            else:
                entry['properties']['runtime_widget_names'].append(name)
                entry['widgets_values'].append(value)
                if 'seed' in name:
                    entry['properties']['runtime_widget_names'].append(None)
                    entry['widgets_values'].append('fixed')
        nodes.append(entry)
        by_id[key] = entry
    for key, node in graph.items():
        for name, value in node['inputs'].items():
            if not isinstance(value, list):
                continue
            source, slot = value
            target_slot = next(i for i, item in enumerate(by_id[key]['inputs']) if item['name'] == name)
            link_id = len(links) + 1
            kind = by_id[source]['outputs'][slot]['type']
            links.append([link_id, int(source), slot, int(key), target_slot, kind])
            by_id[key]['inputs'][target_slot]['link'] = link_id
            by_id[source]['outputs'][slot]['links'].append(link_id)
    return {'last_node_id': max(map(int, graph)), 'last_link_id': len(links), 'nodes': nodes,
            'links': links, 'groups': [], 'config': {}, 'extra': {'ds': {'scale': 0.55, 'offset': [50, 50]}}, 'version': 0.4}


def from_editor(editor):
    links = {item[0]: item for item in editor['links']}
    graph = {}
    for node in editor['nodes']:
        values = {name: value for name, value in zip(node['properties']['runtime_widget_names'], node['widgets_values']) if name}
        for item in node['inputs']:
            link = links[item['link']]
            values[item['name']] = [str(link[1]), link[2]]
        graph[str(node['id'])] = {'class_type': node['type'], 'inputs': values}
    return graph
