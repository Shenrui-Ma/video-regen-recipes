#!/usr/bin/env python3
"""One explicit NovelAI generation; no retries, redirects, credentials on disk, or dependencies."""
import argparse
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import sys
import urllib.error
import urllib.request
import zipfile
import zlib

ENDPOINT = "https://image.novelai.net/ai/generate-image"
MAX_BYTES = 32 * 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n"
PARAMETERS = set("width height n_samples steps scale sampler seed negative_prompt image_format params_version noise_schedule cfg_rescale sm sm_dyn dynamic_thresholding qualityToggle ucPreset legacy legacy_v3_extend deliberate_euler_ancestral_bug prefer_brownian skip_cfg_above_sigma v4_prompt v4_negative_prompt image strength noise extra_noise_seed color_correct".split())


class SafeError(Exception):
    """An error whose message never contains server bodies or credentials."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def png_dimensions(data):
    if not data.startswith(PNG):
        raise SafeError("Expected a PNG image.")
    pos, dimensions, has_data = 8, None, False
    while pos + 12 <= len(data):
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        end = pos + 8 + size
        if end + 4 > len(data) or zlib.crc32(data[pos + 4:end]) != struct.unpack(">I", data[end:end + 4])[0]:
            raise SafeError("PNG is truncated or has an invalid CRC.")
        if dimensions is None:
            if kind != b"IHDR" or size != 13:
                raise SafeError("PNG has no valid IHDR.")
            dimensions = struct.unpack(">II", data[pos + 8:pos + 16])
            if not all(0 < n <= 4096 for n in dimensions):
                raise SafeError("PNG dimensions exceed this client's limit.")
        has_data |= kind == b"IDAT"
        pos = end + 4
        if kind == b"IEND":
            if size != 0 or pos != len(data) or not has_data:
                raise SafeError("PNG has an invalid ending.")
            return dimensions
    raise SafeError("PNG has no complete ending.")


def validate(body):
    if not isinstance(body, dict) or set(body) != {"input", "model", "action", "parameters"}:
        raise SafeError("Request must contain only input, model, action, parameters.")
    if not isinstance(body["input"], str) or not body["input"].strip():
        raise SafeError("A nonempty input prompt is required.")
    if not isinstance(body["model"], str) or not re.fullmatch(r"nai-diffusion-[a-z0-9-]+", body["model"]):
        raise SafeError("Supply a verified NovelAI model API ID; display names/placeholders are invalid.")
    if body["action"] not in ("generate", "img2img"):
        raise SafeError("This client supports only generate and img2img.")
    p = body["parameters"]
    if not isinstance(p, dict) or set(p) - PARAMETERS:
        raise SafeError("Unknown/unsupported parameter: review official schema; do not silently remove it.")
    for key in ("width", "height"):
        if type(p.get(key)) is not int or not 64 <= p[key] <= 2048 or p[key] % 64:
            raise SafeError("Width/height must be multiples of 64 in this client's 64..2048 range.")
    if p.get("n_samples") != 1 or type(p.get("n_samples")) is not int or p.get("image_format") != "png":
        raise SafeError("This client requires n_samples=1 and image_format=png.")
    if type(p.get("steps")) is not int or not 1 <= p["steps"] <= 50 or not number(p.get("scale"), 0, 20):
        raise SafeError("Explicit steps (1..50) and scale (0..20) are required.")
    if type(p.get("seed")) is not int or not 0 <= p["seed"] < 2**32:
        raise SafeError("An explicit unsigned 32-bit seed is required.")
    if not isinstance(p.get("sampler"), str) or not re.fullmatch(r"[a-z0-9_]+", p["sampler"]):
        raise SafeError("Supply the sampler API name from a verified configuration.")
    if not isinstance(p.get("negative_prompt"), str):
        raise SafeError("negative_prompt must be explicit (may be empty).")
    for key, prompt in (("v4_prompt", body["input"]), ("v4_negative_prompt", p["negative_prompt"])):
        if key in p:
            value = p[key]
            if not isinstance(value, dict) or not isinstance(value.get("caption"), dict):
                raise SafeError("Structured prompt must contain caption.")
            if value["caption"].get("base_caption") != prompt:
                raise SafeError("Structured and flat prompts must agree; update both.")
    if body["action"] == "img2img":
        try:
            raw = base64.b64decode(p.get("image", ""), validate=True)
        except (ValueError, TypeError):
            raise SafeError("image must be raw PNG base64 without a data-URL prefix.") from None
        if len(raw) > MAX_BYTES or png_dimensions(raw) != (p["width"], p["height"]):
            raise SafeError("Prepare a PNG with exactly the requested dimensions before img2img.")
        if not number(p.get("strength"), 0, 1) or not number(p.get("noise"), 0, 1):
            raise SafeError("img2img needs explicit strength and noise in 0..1.")
    elif any(k in p for k in ("image", "strength", "noise", "extra_noise_seed", "color_correct")):
        raise SafeError("Image-to-image fields require action=img2img.")
    try:
        encoded = canonical(body)
    except (ValueError, TypeError):
        raise SafeError("Request must be finite JSON.") from None
    if len(encoded) > MAX_BYTES:
        raise SafeError("Request exceeds this client's size limit.")
    if any(marker in encoded for marker in (b"{{", b"REPLACE_")):
        raise SafeError("Resolve all request placeholders before validation.")
    return encoded


def private_write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def save_state(run_dir, state):
    temporary = run_dir / (".state-" + secrets.token_hex(8))
    private_write(temporary, canonical(state))
    os.replace(temporary, run_dir / "state.json")


def save_response(run_dir, state, data):
    """Publish response bytes and their request binding together, before updating state."""
    receipt = {"schema_version": 1, "request_sha256": state["request_sha256"],
               "correlation_id": state["correlation_id"], "response_sha256": sha(data)}
    temporary = run_dir / (".response-" + secrets.token_hex(8))
    temporary.mkdir(mode=0o700)
    private_write(temporary / "response.zip", data)
    private_write(temporary / "receipt.json", canonical(receipt))
    if (run_dir / "response").exists():
        raise SafeError("A response package already exists; it will not be replaced.")
    # Same-filesystem directory rename makes ZIP and receipt visible as one package.
    os.rename(temporary, run_dir / "response")


def unpack(data, run_dir, body):
    if len(data) > MAX_BYTES:
        raise SafeError("ZIP exceeds size limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise SafeError("Expected exactly one generated image; retain ZIP for inspection.")
            item = members[0]
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.png", item.filename) or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1:
                raise SafeError("Unsafe ZIP member name, link, or encryption.")
            if not 0 < item.file_size <= MAX_BYTES or item.file_size > max(item.compress_size, 1) * 200:
                raise SafeError("Unsafe ZIP expansion size/ratio.")
            raw = archive.read(item)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error):
        raise SafeError("Invalid or unsupported ZIP; retain response for inspection.") from None
    p = body["parameters"]
    if png_dimensions(raw) != (p["width"], p["height"]):
        raise SafeError("Returned image dimensions differ from the request.")
    target = run_dir / "image-001.png"
    if target.exists():
        if target.is_symlink() or sha(target.read_bytes()) != sha(raw):
            raise SafeError("Existing output differs; it will not be overwritten.")
    else:
        private_write(target, raw)
    return [{"file": target.name, "sha256": sha(raw), "width": p["width"], "height": p["height"]}]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SafeError("Redirect rejected; credentials stay on the official endpoint.")


def send(body, run_dir, token, opener=None):
    data = validate(body)
    if not token or any(c.isspace() for c in token):
        raise SafeError("Set NOVELAI_API_KEY to the token only; never print it.")
    try:
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise SafeError("Run directory already exists: inspect state; do not repeat submission.") from None
    state = {"status": "prepared", "request_sha256": sha(data), "correlation_id": "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(6))}
    private_write(run_dir / "request.json", data)
    save_state(run_dir, state)
    request = urllib.request.Request(ENDPOINT, data=data, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/zip", "x-correlation-id": state["correlation_id"]}, method="POST")
    # A crash from this point means submission/charging may have happened.
    state["status"] = "submission_unknown"
    save_state(run_dir, state)
    try:
        client = opener or urllib.request.build_opener(NoRedirect())
        with client.open(request, timeout=180) as response:
            if response.status != 201 or response.headers.get_content_type() != "application/zip":
                raise SafeError("Unexpected status/content type; no automatic retry.")
            result = response.read(MAX_BYTES + 1)
            if len(result) > MAX_BYTES:
                raise SafeError("Response exceeds limit; no automatic retry.")
        save_response(run_dir, state, result)
        state.update(status="response_saved", response_sha256=sha(result))
        save_state(run_dir, state)
        state["images"] = unpack(result, run_dir, body)
        state["status"] = "downloaded_needs_visual_review"
        save_state(run_dir, state)
        return state
    except urllib.error.HTTPError as error:
        state["http_status"] = error.code
        state["status"] = "http_error_review_required"
        save_state(run_dir, state)
        raise SafeError("HTTP error %d; inspect account/configuration; no retry or response-body logging." % error.code) from None
    except (OSError, ValueError, SafeError):
        raise SafeError("Generation did not complete locally. Inspect state.json; never automatically repeat this request.") from None


def recover(run_dir):
    """Only local extraction: never sends a generation request."""
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("status") not in {"submission_unknown", "response_saved", "downloaded_needs_visual_review"}:
        raise SafeError("This submission state cannot be recovered from a local response.")
    body = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    if sha(validate(body)) != state["request_sha256"]:
        raise SafeError("Saved request fingerprint mismatch.")
    package = run_dir / "response"
    if package.is_symlink() or not package.is_dir():
        raise SafeError("No atomically saved response package; a loose ZIP cannot establish request ownership.")
    if any(not (package / name).is_file() or (package / name).is_symlink() for name in ("receipt.json", "response.zip")):
        raise SafeError("Response package needs a regular ZIP and its matching receipt.")
    if (package / "receipt.json").stat().st_size > 4096:
        raise SafeError("Response receipt exceeds size limit.")
    receipt = json.loads((package / "receipt.json").read_text(encoding="utf-8"))
    if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1 or receipt.get("request_sha256") != state["request_sha256"]
            or receipt.get("correlation_id") != state.get("correlation_id") or not state.get("correlation_id")):
        raise SafeError("Response receipt belongs to a different request or submission.")
    with (package / "response.zip").open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or sha(data) != receipt.get("response_sha256"):
        raise SafeError("Response bytes do not match the request-bound receipt.")
    if state.get("response_sha256") and receipt["response_sha256"] != state["response_sha256"]:
        raise SafeError("Saved response fingerprint mismatch.")
    state.update(response_sha256=sha(data), images=unpack(data, run_dir, body), status="downloaded_needs_visual_review")
    save_state(run_dir, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--run-dir", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true", help="Submit one user-authorized generation.")
    modes.add_argument("--recover", action="store_true", help="Extract a saved ZIP locally; never submit.")
    parser.add_argument("--config-verified", action="store_true", help="Model/action/sampler and feature compatibility were verified against official evidence.")
    args = parser.parse_args()
    try:
        if args.recover:
            if not args.run_dir:
                raise SafeError("--recover needs --run-dir.")
            result = recover(args.run_dir)
        else:
            if not args.request or args.request.stat().st_size > MAX_BYTES:
                raise SafeError("Supply a request JSON below 32 MiB.")
            body = json.loads(args.request.read_text(encoding="utf-8"))
            data = validate(body)
            if args.execute:
                if not args.run_dir or not args.config_verified:
                    raise SafeError("Execution requires --run-dir and --config-verified after official evidence review.")
                result = send(body, args.run_dir, os.environ.get("NOVELAI_API_KEY", ""))
            else:
                result = {"status": "dry_run_only", "request_sha256": sha(data), "model": body["model"], "action": body["action"], "n_samples": 1, "no_network_request": True}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SafeError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError):
        print("Invalid local input/state or inaccessible file; no details printed to protect private data.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
