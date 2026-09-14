"""Portable bindings and LiteGraph editor export for the successful Core AV pattern."""
import copy
import json
from pathlib import Path
import sys

TEMPLATE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TEMPLATE / 'scripts'))
from plan_segments import plan_segments


def load(name):
    return json.loads((TEMPLATE / 'workflows' / name).read_text(encoding='utf-8'))


def build(row, character, reference, description, seed, video=None, audio=None,
          prefix='heartache', models=None):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('SEED_MUST_BE_UINT64')
    if row['sample_frames'] < 5 or row['sample_frames'] % 17 != 5:
        raise ValueError('FRAME_GRID')
    if row['visible_frames'] < 1 or row['publish_end'] != row['head_trim_frames'] + row['visible_frames'] or row['publish_end'] > row['sample_frames']:
        raise ValueError('PUBLISH_RANGE')
    continuation = row['predecessor'] is not None
    g = load(('continue' if continuation else 'first') + '.api.json')
    g['21']['inputs']['image'] = character
    g['22']['inputs']['file'] = reference
    g['6']['inputs']['noise_seed'] = seed
    g['5']['inputs']['length'] = row['sample_frames']
    g['54']['inputs']['length'] = row['visible_frames']
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
    g['5']['inputs']['prompt'] = text
    for node, part in [('61', 'video'), ('62', 'audio'), ('14', 'silent')]:
        g[node]['inputs']['filename_prefix'] = f"{prefix}/seg{row['segment']:02d}-{part}"
    if continuation:
        if not video or not audio or str(row['head_trim_frames']) not in ('5', '22', '39', '56'):
            raise ValueError('CONTINUATION_REQUIRES_BOTH_PARTS_AND_SUPPORTED_CONTEXT')
        g['51']['inputs']['latent'] = video
        g['52']['inputs']['latent'] = audio
        g['53']['inputs']['context_length'] = str(row['head_trim_frames'])
    elif row['head_trim_frames'] != 0:
        raise ValueError('FIRST_HAS_CONTEXT')
    for key, value in (models or {}).items():
        node, field = {'transformer': ('1', 'unet_name'), 'text_encoder': ('2', 'clip_name'),
                       'video_vae': ('3', 'vae_name'), 'audio_vae': ('4', 'vae_name')}[key]
        g[node]['inputs'][field] = value
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
