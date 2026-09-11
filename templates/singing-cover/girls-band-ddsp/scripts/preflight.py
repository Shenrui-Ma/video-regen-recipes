#!/usr/bin/env python3
"""Read-only model inventory planning and byte checks; never runs inference."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


TEMPLATE = Path(__file__).resolve().parents[1]


def validate_artifacts(artifacts):
    seen = set()
    for artifact in artifacts:
        raw = artifact["path"]
        if not isinstance(raw, str) or not raw:
            raise ValueError("artifact path must be a nonempty string")
        path = PurePosixPath(raw)
        if (
            path.is_absolute()
            or any(part in ("", ".", "..") for part in raw.split("/"))
            or "\\" in raw
            or ":" in raw
            or any(ord(char) < 32 for char in raw)
        ):
            raise ValueError("artifact path must be a safe relative POSIX path")
        if raw in seen:
            raise ValueError("duplicate artifact path")
        seen.add(raw)
        if not isinstance(artifact["sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", artifact["sha256"]
        ):
            raise ValueError("artifact must have a complete lowercase SHA-256")
        size = artifact["bytes"]
        if size is not None and (type(size) is not int or size <= 0):
            raise ValueError("artifact bytes must be a positive integer or null")


def build_plan(voice_id, ddsp_only=False):
    voices = json.loads((TEMPLATE / "model-catalog/voices.json").read_text(encoding="utf-8"))
    deps = json.loads((TEMPLATE / "model-catalog/dependencies.json").read_text(encoding="utf-8"))
    if voices["schema_version"] != 1 or deps["schema_version"] != 1:
        raise ValueError("unsupported manifest schema")
    if voices["compatibility_profile"] != deps["compatibility_profile"]:
        raise ValueError("incompatible manifests")
    ids = [voice["id"] for voice in voices["voices"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate voice id")
    if voice_id not in ids:
        raise ValueError("unknown voice id")
    voice = voices["voices"][ids.index(voice_id)]
    artifacts = [dict(voice[key]) for key in ("checkpoint", "config")]
    for dependency in deps["dependencies"]:
        if dependency["stage"] not in ("ddsp", "separation"):
            raise ValueError("unknown dependency stage")
        if not ddsp_only or dependency["stage"] == "ddsp":
            artifacts.extend(dict(item) for item in dependency["artifacts"])
    validate_artifacts(artifacts)
    return {
        "schema_version": 1,
        "template_id": "girls-band-ddsp-cover",
        "status": "plan-only",
        "executable": False,
        "gpu_inference": "not-run",
        "listening_review": "pending",
        "voice_id": voice_id,
        "compatibility_profile": voices["compatibility_profile"],
        "scope": "ddsp-only" if ddsp_only else "ddsp-and-separation",
        "manual_gates": [
            "Review source, recording, character and each model's rights.",
            "Verify Linux CUDA runtime, pinned source and actual model path bindings.",
            "Listen to candidates; freeze lead/backing identity and raw/dereverb choice.",
            "Approve short dry conversions before full-song inference.",
            "Align samples, mix, independently measure and listen before delivery.",
        ],
        "artifacts": artifacts,
    }


def check_artifacts(root, artifacts):
    validate_artifacts(artifacts)
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("model root must be an existing directory")
    results = []
    for artifact in artifacts:
        result = {"path": artifact["path"], "status": "unreadable"}
        try:
            target = (root / artifact["path"]).resolve(strict=True)
            if not target.is_relative_to(root):
                result["status"] = "outside-model-root"
            elif not target.is_file():
                result["status"] = "not-a-file"
            else:
                digest = hashlib.sha256()
                size = 0
                with target.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                        size += len(block)
                actual_hash = digest.hexdigest()
                result.update(bytes=size, sha256=actual_hash)
                size_ok = artifact["bytes"] is None or size == artifact["bytes"]
                result["status"] = (
                    "match" if size_ok and actual_hash == artifact["sha256"] else "mismatch"
                )
        except FileNotFoundError:
            result["status"] = "missing"
        except (OSError, RuntimeError):
            # Avoid leaking absolute private paths from OS error messages.
            result["status"] = "unreadable"
        results.append(result)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", required=True, help="Exact voice id from voices.json")
    parser.add_argument("--check", action="store_true", help="Read model bytes; no inference")
    parser.add_argument("--model-root", type=Path, help="Root containing voices/pretrain/separation")
    parser.add_argument("--ddsp-only", action="store_true", help="Omit separation model checks")
    args = parser.parse_args(argv)
    if args.check != (args.model_root is not None):
        parser.error("--check and --model-root must be supplied together")
    try:
        plan = build_plan(args.voice, args.ddsp_only)
        if args.check:
            plan["checks"] = check_artifacts(args.model_root, plan["artifacts"])
            matched = all(item["status"] == "match" for item in plan["checks"])
            plan["status"] = "byte-integrity-checked" if matched else "byte-integrity-failed"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 1 if plan["status"] == "byte-integrity-failed" else 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError):
        print(json.dumps({"status": "invalid-input", "error": "Check voice id, manifests and model root; no inference ran."}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
