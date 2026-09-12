#!/usr/bin/env python3
"""Offline, content-based receipts; no process launch or model deserialization."""

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def require_regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Expected a regular, non-symlink file")
    if path.stat().st_size == 0:
        raise ValueError("Empty file is not a completed artifact")


def resource_path(base, raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("Resource paths must be nonempty strings")
    path = base / raw
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Symlink resources are not accepted; bind the real file")
    return path.resolve(strict=True)


def fingerprint(spec_path, receipt_path):
    spec_path = spec_path.resolve(strict=True)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or set(spec) != {"schema_version", "parameters", "resources"}:
        raise ValueError("Spec requires exactly schema_version, parameters, resources")
    if spec["schema_version"] != 1 or not isinstance(spec["parameters"], dict):
        raise ValueError("Expected schema_version=1 and parameters object")
    resources = spec["resources"]
    if not isinstance(resources, dict) or not resources:
        raise ValueError("At least one named resource is required")
    receipt_path = receipt_path.resolve()
    result = {}
    for name, raw in sorted(resources.items()):
        if not name or not isinstance(name, str):
            raise ValueError("Resource names must be nonempty strings")
        path = resource_path(spec_path.parent, raw)
        if path == receipt_path or (path.is_dir() and receipt_path.is_relative_to(path)):
            raise ValueError("Receipt must be outside every hashed resource")
        if path.is_dir():
            entries = {}
            for item in sorted(path.rglob("*")):
                if item.is_symlink():
                    raise ValueError("Symlinks inside resource trees are not accepted")
                if item.is_dir():
                    continue
                require_regular(item)
                entries[item.relative_to(path).as_posix()] = {
                    "bytes": item.stat().st_size, "sha256": sha256(item)}
            if not entries:
                raise ValueError("Resource tree contains no files")
            result[name] = {"kind": "tree", "files": entries}
        else:
            require_regular(path)
            result[name] = {"kind": "file", "bytes": path.stat().st_size,
                            "sha256": sha256(path)}
    body = {"schema_version": 1, "parameters": spec["parameters"], "resources": result}
    return {**body, "fingerprint_sha256": hashlib.sha256(canonical(body)).hexdigest()}


def write_new_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot", help="Hash immutable inputs into a new receipt")
    snapshot.add_argument("--spec", type=Path, required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check", help="Compare current bytes and parameters to a receipt")
    check.add_argument("--spec", type=Path, required=True)
    check.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt_path = args.output if args.command == "snapshot" else args.receipt
        current = fingerprint(args.spec, receipt_path)
        if args.command == "snapshot":
            write_new_json(receipt_path, current)
            print(json.dumps({"status": "snapshotted", "fingerprint_sha256": current["fingerprint_sha256"]}))
        else:
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            if saved != current:
                print(json.dumps({"status": "stale", "action": "Do not reuse downstream artifacts"}))
                return 1
            print(json.dumps({"status": "matched", "not_proven": ["authorization", "stage_completion", "quality"]}))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
