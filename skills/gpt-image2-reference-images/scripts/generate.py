#!/usr/bin/env python3
"""One official Image 2 high request, with offline planning and local recovery."""
import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import urllib.error
import urllib.request
import zlib

ENDPOINT = "https://api.openai.com/v1/responses"
MAX_REF_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 128 * 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value, exclusive=False):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if exclusive:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(text)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        if temporary.is_symlink():
            raise ValueError("unexpected symlink in run directory")
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)


def parse_size(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+x[0-9]+", value):
        raise ValueError("size must be an explicit WIDTHxHEIGHT")
    w, h = map(int, value.split("x"))
    if min(w, h) <= 0 or w % 16 or h % 16 or max(w, h) > 3840:
        raise ValueError("size edges must be positive multiples of 16, at most 3840")
    if max(w, h) > 3 * min(w, h) or not 655360 <= w * h <= 8294400:
        raise ValueError("size ratio or pixel count is outside Image 2 limits")
    return w, h


def png_dimensions(data):
    """Validate chunk bounds/CRC and basic PNG structure; not a full pixel decoder."""
    if not data.startswith(PNG):
        raise ValueError("output is not PNG")
    offset, dims, has_data, ended = 8, None, False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + length + 12
        if end > len(data):
            raise ValueError("truncated PNG data")
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ValueError("PNG checksum mismatch")
        if dims is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("missing PNG header")
            w, h, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if not w or not h or w * h > 8294400 or depth not in valid_depths.get(color, set()):
                raise ValueError("invalid PNG dimensions or color format")
            if compression or filtering or interlace not in (0, 1):
                raise ValueError("unsupported PNG header")
            dims = [w, h]
        elif kind == b"IHDR":
            raise ValueError("duplicate PNG header")
        if kind == b"IDAT" and length:
            has_data = True
        if kind == b"IEND":
            if length or end != len(data) or not has_data:
                raise ValueError("invalid PNG end")
            ended = True
            break
        offset = end
    if not ended:
        raise ValueError("incomplete PNG")
    return dims


def build_request(task_path, response_model):
    if not response_model or response_model.startswith("gpt-image") or "<" in response_model:
        raise ValueError("provide an available language model with image-generation tool support")
    task = json.loads(task_path.read_text(encoding="utf-8"))
    if not isinstance(task, dict) or set(task) - {"prompt_file", "size", "references"}:
        raise ValueError("task accepts only prompt_file, size, references")
    prompt_path = task_path.parent / task["prompt_file"]
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt or "{{" in prompt or "}}" in prompt:
        raise ValueError("prompt is empty or contains unresolved placeholders")
    size = task.get("size", "1536x1024")
    parse_size(size)
    references = task.get("references", [])
    if not isinstance(references, list) or len(references) > 4:
        raise ValueError("references must be a list of at most four images")
    content = [{"type": "input_text", "text": prompt}]
    records = []
    for number, ref in enumerate(references, 1):
        if not isinstance(ref, dict) or set(ref) != {"path", "role"}:
            raise ValueError("each reference requires only path and role")
        role = ref["role"]
        if role not in {"identity", "outfit", "scene", "pose", "style", "edit_base"}:
            raise ValueError("unsupported reference role")
        path = task_path.parent / ref["path"]
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_REF_BYTES:
            raise ValueError("reference missing or exceeds the per-file size limit")
        raw = path.read_bytes()
        if len(raw) > MAX_REF_BYTES:
            raise ValueError("reference changed size while reading")
        if raw.startswith(PNG):
            png_dimensions(raw)
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9"):
            mime = "image/jpeg"
        else:
            raise ValueError("reference must be a readable PNG or JPEG; inspect it before submitting")
        content.extend([
            {"type": "input_text", "text": f"Image {number}: {role} reference."},
            {"type": "input_image", "image_url": f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")},
        ])
        records.append({"index": number, "role": role, "path": ref["path"], "sha256": digest(raw), "bytes": len(raw)})
    body = {
        "model": response_model,
        "store": False,
        "stream": False,
        "max_tool_calls": 1,
        "parallel_tool_calls": False,
        "input": [{"role": "user", "content": content}],
        "tools": [{"type": "image_generation", "model": "gpt-image-2", "quality": "high", "size": size, "output_format": "png"}],
        "tool_choice": {"type": "image_generation"},
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    plan = {"state": "prepared", "request_sha256": digest(encoded), "response_model": response_model,
            "image_model": "gpt-image-2", "quality": "high", "requested_size": size, "references": records}
    return encoded, plan, prompt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_once(payload, key):
    request = urllib.request.Request(ENDPOINT, data=payload, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=600) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeded local size limit")
        return json.loads(raw), response.headers.get("x-request-id")


def extract_result(response):
    if not isinstance(response, dict) or response.get("status") != "completed":
        raise ValueError("response has not completed")
    output = response.get("output")
    if not isinstance(output, list):
        raise ValueError("response has no output list")
    calls = [item for item in output if isinstance(item, dict) and item.get("type") == "image_generation_call"]
    if len(calls) != 1 or calls[0].get("status") != "completed" or not calls[0].get("result"):
        raise ValueError("expected exactly one completed image result")
    call = calls[0]
    if call.get("quality", "high") != "high":
        raise ValueError("returned image quality differs from high")
    if call.get("model", "gpt-image-2") not in {"gpt-image-2", "gpt-image-2-2026-04-21"}:
        raise ValueError("returned image model differs from requested Image 2")
    data = base64.b64decode(call["result"], validate=True)
    dims = png_dimensions(data)
    return data, dims, call


def finish(run_dir, manifest, response):
    try:
        data, dims, call = extract_result(response)
    except (ValueError, TypeError, binascii.Error):
        manifest["state"] = "invalid_output"
        write_json(run_dir / "manifest.json", manifest)
        raise ValueError("saved response has no single valid completed PNG; inspect locally") from None
    output_path = run_dir / "image.png"
    if output_path.is_symlink():
        raise ValueError("unexpected output symlink")
    if output_path.exists():
        if output_path.read_bytes() != data:
            raise ValueError("existing image differs; refusing to overwrite")
    else:
        temporary = run_dir / "image.png.part"
        if temporary.is_symlink():
            raise ValueError("unexpected output symlink")
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output_path)
    manifest.update({"state": "generated", "response_id": response.get("id"), "image_call_id": call.get("id"),
                     "revised_prompt": call.get("revised_prompt"), "usage": response.get("usage"),
                     "returned_settings": {key: call.get(key) for key in ("model", "quality", "size", "output_format")},
                     "output": {"file": "image.png", "sha256": digest(data), "bytes": len(data), "dimensions": dims},
                     "size_matches": dims == list(parse_size(manifest["requested_size"])),
                     "visual_review": "pending"})
    write_json(run_dir / "manifest.json", manifest)


def run(task_path, response_model, run_dir, execute=False, recover=False):
    if recover:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("state") not in {"submitting", "unknown", "response_received", "invalid_output", "generated"}:
            raise ValueError("run has no submitted response to recover")
        if (run_dir / "submission.lock").read_text() != manifest.get("request_sha256"):
            raise ValueError("submission fingerprint mismatch")
        envelope = json.loads((run_dir / "response.json").read_text(encoding="utf-8"))
        if envelope.get("request_sha256") != manifest.get("request_sha256"):
            raise ValueError("response belongs to a different request")
        response = envelope["response"]
        response_hash = digest(json.dumps(response, sort_keys=True, ensure_ascii=False).encode())
        if response_hash != envelope.get("response_sha256") or manifest.get("response_sha256", response_hash) != response_hash:
            raise ValueError("saved response checksum mismatch")
        manifest.update(request_id=envelope.get("request_id"), response_sha256=response_hash)
        finish(run_dir, manifest, response)
        return "recovered locally; visual review required"
    payload, plan, prompt = build_request(task_path, response_model)
    run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = run_dir / "manifest.json"
    if state_path.exists():
        manifest = json.loads(state_path.read_text(encoding="utf-8"))
        if manifest.get("request_sha256") != plan["request_sha256"]:
            raise ValueError("run directory belongs to different inputs; use a new directory")
    else:
        if any(run_dir.iterdir()):
            raise ValueError("new run directory must be empty")
        write_json(state_path, plan, exclusive=True)
        manifest = plan
        with os.fdopen(os.open(run_dir / "prompt.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(prompt + "\n")
    if not execute:
        return "local checks passed; state=" + manifest["state"] + "; no request sent"
    if manifest["state"] != "prepared":
        raise ValueError("this run was already submitted; recover existing results, do not resubmit")
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key or any(c.isspace() for c in key):
        raise ValueError("configure OPENAI_API_KEY in the process environment")
    # Never remove this marker: it also prevents duplicate submission after a crash.
    with (run_dir / "submission.lock").open("x", encoding="utf-8") as lock:
        lock.write(plan["request_sha256"])
    manifest["state"] = "submitting"
    write_json(state_path, manifest)
    try:
        response, request_id = post_once(payload, key)
    except urllib.error.HTTPError as exc:
        manifest.update({"state": "rejected" if 400 <= exc.code < 500 and exc.code != 408 else "unknown", "http_status": exc.code})
        write_json(state_path, manifest)
        raise ValueError(f"HTTP {exc.code}; no automatic retry; inspect access, parameters or service status") from None
    except Exception:
        manifest["state"] = "unknown"
        write_json(state_path, manifest)
        raise ValueError("response unavailable; generation outcome unknown; no automatic retry") from None
    response_hash = digest(json.dumps(response, sort_keys=True, ensure_ascii=False).encode())
    envelope = {"request_sha256": manifest["request_sha256"], "response_sha256": response_hash, "request_id": request_id, "response": response}
    if (run_dir / "response.json").exists():
        raise ValueError("unexpected saved response; refusing to overwrite")
    write_json(run_dir / "response.json", envelope)
    manifest.update({"state": "response_received", "request_id": request_id, "response_sha256": response_hash})
    write_json(state_path, manifest)
    finish(run_dir, manifest, response)
    return "image saved; check size_matches and complete visual review"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--response-model", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    try:
        print(run(args.task, args.response_model, args.run_dir, args.execute, args.recover))
    except ValueError as exc:
        # All request errors above are replaced with local messages, never raw server bodies.
        print("Stopped: " + str(exc), file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError):
        print("Stopped: check task fields, input files and local manifest. No automatic retry.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
