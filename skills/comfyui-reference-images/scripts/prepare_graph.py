#!/usr/bin/env python3
"""Bind a ComfyUI API template offline. Never submits or runs a workflow."""

import argparse
import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


TOKEN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
OUTPUT_CLASSES = {"SaveImage", "SaveVideo", "VHS_VideoCombine",
                  "SaveAnimatedPNG", "SaveAnimatedWEBP"}
MODEL_FIELDS = {"ckpt_name", "unet_name", "model_name", "vae_name", "clip_name",
                "clip_name1", "clip_name2", "clip_name3", "lora_name",
                "control_net_name"}
INTEGER_FIELDS = {"width", "height", "length", "batch_size", "steps"}
SEED_FIELDS = {"seed", "noise_seed"}


def read_json(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object, parse_constant=invalid_constant)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or "{{" in key or "}}" in key:
                raise ValueError("JSON keys must be strings without placeholders")
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite numeric value")


def bind(template, values):
    if not isinstance(values, dict):
        raise ValueError("values must be a JSON object")
    required = {match.group(1) for text in strings(template)
                for match in TOKEN.finditer(text)}
    missing = required - values.keys()
    extra = values.keys() - required
    if missing or extra:
        raise ValueError(f"parameter mismatch: missing={sorted(missing)}, extra={sorted(extra)}")

    def replace(value):
        if isinstance(value, str):
            entire = TOKEN.fullmatch(value)
            if entire:
                return copy.deepcopy(values[entire.group(1)])

            def embedded(match):
                item = values[match.group(1)]
                if not isinstance(item, str):
                    raise ValueError(f"embedded parameter must be a string: {match.group(1)}")
                return item

            return TOKEN.sub(embedded, value)
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return value

    graph = replace(template)
    if any("{{" in text or "}}" in text for text in strings(graph)):
        raise ValueError("unresolved or malformed placeholder; values are not recursively expanded")
    return graph


def relative_name(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected a nonempty relative filename or prefix")
    normalized = value.replace("\\", "/")
    if (normalized.startswith("/") or ":" in normalized or "\x00" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))):
        raise ValueError(f"{label}: absolute paths and path traversal are not allowed")


def validate_graph(graph, output_node):
    if not isinstance(graph, dict) or not graph:
        raise ValueError("template must be a nonempty ComfyUI API node map")
    dependencies = {}
    for node_id, node in graph.items():
        if not isinstance(node_id, str) or not node_id.strip() or not isinstance(node, dict):
            raise ValueError("invalid API node ID or node object")
        if not isinstance(node.get("class_type"), str) or not node["class_type"].strip():
            raise ValueError(f"{node_id}: missing class_type (editor JSON is not an API graph)")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise ValueError(f"{node_id}: inputs must be an object")
        dependencies[node_id] = set()
        for name, value in inputs.items():
            label = f"{node_id}.{name}"
            if isinstance(value, list):
                if (len(value) != 2 or not isinstance(value[0], str)
                        or value[0] not in graph or type(value[1]) is not int or value[1] < 0):
                    raise ValueError(f"{label}: invalid [node_id, output_slot] edge")
                dependencies[node_id].add(value[0])
                continue
            if name in SEED_FIELDS:
                if type(value) is not int or not 0 <= value <= 2**64 - 1:
                    raise ValueError(f"{label}: seed must be an integer in [0, 2^64-1]")
            if name in INTEGER_FIELDS and (type(value) is not int or value <= 0):
                raise ValueError(f"{label}: expected a positive JSON integer")
            if name in MODEL_FIELDS or name == "filename_prefix":
                relative_name(value, label)
            if node["class_type"] == "LoadImage" and name == "image":
                relative_name(value, label)
    if output_node not in graph:
        raise ValueError(f"output node does not exist: {output_node}")
    output = graph[output_node]
    if output["class_type"] not in OUTPUT_CLASSES:
        raise ValueError(f"unsupported output class: {output['class_type']}")
    media_input = "video" if output["class_type"] == "SaveVideo" else "images"
    if not isinstance(output["inputs"].get(media_input), list):
        raise ValueError(f"output node requires a connected {media_input} input")
    if output["class_type"] == "VHS_VideoCombine" and output["inputs"].get("save_output") is not True:
        raise ValueError("VHS_VideoCombine requires save_output=true")

    # Iterative DFS also detects cycles without depending on Python's recursion limit.
    visiting, visited = set(), set()
    stack = [(output_node, False)]
    while stack:
        node_id, closing = stack.pop()
        if closing:
            visiting.remove(node_id)
            visited.add(node_id)
            continue
        if node_id in visiting:
            raise ValueError(f"cycle detected at node {node_id}")
        if node_id in visited:
            continue
        visiting.add(node_id)
        stack.append((node_id, True))
        stack.extend((source, False) for source in sorted(dependencies[node_id]))
    unused = graph.keys() - visited
    if unused:
        raise ValueError(f"nodes do not contribute to target output: {sorted(unused)}")
    return graph


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_exclusive(files):
    """Reserve every destination before writing; clean up only files created here."""
    handles = []
    try:
        for path, content in files:
            handles.append((path, path.open("xb"), content))
        for _, handle, content in handles:
            handle.write(content)
            handle.flush()
    except BaseException:
        for path, handle, _ in handles:
            handle.close()
            path.unlink(missing_ok=True)
        raise
    finally:
        for _, handle, _ in handles:
            handle.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--values", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-node", required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        graph = validate_graph(bind(read_json(args.template), read_json(args.values)), args.output_node)
        content = encoded(graph)
        digest = hashlib.sha256(content).hexdigest()
        files = [(args.output, content)]
        if args.manifest:
            manifest = {
                "schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "state": "prepared",
                "graph_sha256": digest,
                "output_node": args.output_node,
                "output_class": graph[args.output_node]["class_type"],
                "prompt_id": None,
                "client_id": None,
                "visual_review": "pending",
                "object_info_checked": False,
                "inference_performed": False,
                "outputs": [],
            }
            files.append((args.manifest, encoded(manifest)))
        write_exclusive(files)
    except (ValueError, OSError, TypeError) as error:
        parser.exit(2, f"prepare_graph: {error}\n")
    print(json.dumps({"state": "prepared", "graph_sha256": digest,
                      "output_node": args.output_node}, ensure_ascii=False))


if __name__ == "__main__":
    main()
