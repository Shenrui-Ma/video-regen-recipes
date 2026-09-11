#!/usr/bin/env python3
"""Submit one ComfyUI API graph once; resume, download and inspect its result.

Python standard library; local ffprobe and ffmpeg are required. No model install,
asset upload, queue clearing, automatic resubmission, or media repair is performed.
"""

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from fractions import Fraction


class ShotError(Exception):
    """A deliberately sanitized user-facing diagnostic."""


class Pending(ShotError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ShotError("Cannot read valid JSON from the specified local file.") from None


def endpoint_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ShotError("COMFY_BASE_URL must be an HTTP(S) base URL without credentials, query or fragment.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise ShotError("COMFY_BASE_URL has an invalid port.") from None
    host = parsed.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{host}:{port}{parsed.path.rstrip('/')}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ShotError("HTTP redirect refused; configure the final ComfyUI base URL directly.")


class Client:
    def __init__(self, base_url, seconds=60, token=None):
        self.base_url = endpoint_url(base_url)
        self.endpoint_sha256 = digest(self.base_url)
        self.deadline = time.monotonic() + seconds
        self.token = token
        host = urllib.parse.urlsplit(self.base_url).hostname
        if token and self.base_url.startswith("http:") and host not in ("127.0.0.1", "::1", "localhost"):
            raise ShotError("Remote bearer authentication requires HTTPS.")
        self.opener = urllib.request.build_opener(NoRedirect())

    def remaining(self):
        seconds = self.deadline - time.monotonic()
        if seconds <= 0:
            raise Pending("Time budget reached; resume this run directory.")
        return seconds

    def open(self, path, data=None, headers=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ShotError("Invalid API route.")
        outgoing = {"Accept-Encoding": "identity", **(headers or {})}
        if self.token:
            outgoing["Authorization"] = "Bearer " + self.token
        if data is not None:
            outgoing["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=outgoing)
        try:
            return self.opener.open(request, timeout=min(15, self.remaining()))
        except urllib.error.HTTPError as error:
            raise ShotError(f"ComfyUI returned HTTP {error.code}; inspect its UI without logging credentials.") from None
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            raise Pending("Connection interrupted; resume the existing run, never submit it again.") from None

    def json(self, path, data=None):
        with self.open(path, canonical(data) if data is not None else None) as response:
            try:
                raw = response.read(64 * 1024 * 1024 + 1)
                if len(raw) > 64 * 1024 * 1024:
                    raise ShotError("API JSON exceeds the 64 MiB safety limit.")
                result = json.loads(raw)
            except (ValueError, http.client.HTTPException, OSError):
                raise Pending("Incomplete or invalid JSON response; resume the existing run.") from None
        if not isinstance(result, dict):
            raise ShotError("Unexpected API response shape.")
        return result

    def identity(self):
        stats = self.json("/system_stats")
        system = stats.get("system", {})
        stable = {key: system.get(key) for key in ("os", "python_version", "comfyui_version", "pytorch_version")}
        devices = [{key: device.get(key) for key in ("name", "type", "index", "vram_total")}
                   for device in stats.get("devices", [])]
        return digest({"endpoint": self.endpoint_sha256, "system": stable, "devices": devices})


def is_link(value):
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[0], str) and type(value[1]) is int)


def check_graph(graph, output_node):
    if not isinstance(graph, dict) or not graph or "nodes" in graph:
        raise ShotError("Expected a rendered ComfyUI API graph, not an editor workflow.")
    def unresolved(value):
        if isinstance(value, str):
            return "{{" in value or "}}" in value
        if isinstance(value, dict):
            return any(unresolved(item) for item in value.values())
        if isinstance(value, list):
            return any(unresolved(item) for item in value)
        return False
    if unresolved(graph):
        raise ShotError("Workflow still contains unresolved template placeholders.")
    for node_id, node in graph.items():
        if not isinstance(node, dict) or not isinstance(node.get("class_type"), str) or not isinstance(node.get("inputs"), dict):
            raise ShotError("Each API node must have class_type and inputs.")
        for value in node["inputs"].values():
            if is_link(value) and (value[0] not in graph or value[1] < 0):
                raise ShotError("Workflow has an invalid node connection.")
    if graph.get(output_node, {}).get("class_type") != "SaveVideo":
        raise ShotError("The selected output node must be a SaveVideo node.")


def check_expected(graph, expected):
    for node in graph.values():
        inputs = node["inputs"]
        if node["class_type"] == "MiniMaxH3ReferenceToVideo":
            for key, expected_key in (("length", "frames"), ("width", "width"), ("height", "height")):
                if inputs.get(key) != expected[expected_key]:
                    raise ShotError("H3 graph parameters differ from the expected shot plan; correct them before submission.")
        if node["class_type"] == "CreateVideo" and inputs.get("fps") != expected["fps"]:
            raise ShotError("CreateVideo FPS differs from the expected shot plan.")


def expanded_inputs(declared):
    """Expand only slots explicitly authorized by official v3 Autogrow schemas."""
    expanded = {"required": {}, "optional": {}}
    for group in expanded:
        for key, spec in declared.get(group, {}).items():
            if not isinstance(spec, list) or not spec or spec[0] != "COMFY_AUTOGROW_V3":
                expanded[group][key] = spec
                continue
            try:
                template = spec[1]["template"]
                minimum = template["min"]
                if "names" in template:
                    names = template["names"]
                else:
                    maximum = template["max"]
                    if type(maximum) is not int or not 1 <= maximum <= 100:
                        raise ValueError
                    names = [template["prefix"] + str(index) for index in range(maximum)]
                if (not isinstance(names, list) or not 0 < len(names) <= 100
                        or type(minimum) is not int or not 0 <= minimum <= len(names)
                        or any(not isinstance(name, str) or not name or "." in name for name in names)):
                    raise ValueError
                children = template["input"]
                # Official expansion selects the first nonempty required/optional group.
                child_group, child_values = next((kind, values) for kind, values in children.items()
                                                if kind in expanded and values)
                child_spec = next(iter(child_values.values()))
                if not isinstance(child_spec, list) or not child_spec:
                    raise ValueError
                for index, name in enumerate(names):
                    target = "required" if index < minimum and child_group == "required" else "optional"
                    expanded[target][key + "." + name] = child_spec
            except (KeyError, IndexError, TypeError, ValueError, StopIteration):
                raise ShotError("Unsupported or malformed Autogrow schema; compare the installed ComfyUI version.") from None
    return expanded


def preflight(client, graph):
    info = client.json("/object_info")
    for node in graph.values():
        name = node["class_type"]
        schema = info.get(name)
        if not isinstance(schema, dict):
            raise ShotError(f"Missing ComfyUI node class: {name}.")
        declared = expanded_inputs(schema.get("input", {}))
        required = declared.get("required", {})
        optional = declared.get("optional", {})
        inputs = node["inputs"]
        for key in required:
            if key not in inputs:
                raise ShotError(f"Missing required input: {name}.{key}.")
        for key, value in inputs.items():
            spec = {**required, **optional}.get(key)
            if spec is None:
                raise ShotError(f"Unknown node input: {name}.{key}; compare the installed node version.")
            if is_link(value):
                upstream = graph[value[0]]["class_type"]
                outputs = info.get(upstream, {}).get("output", [])
                if value[1] >= len(outputs):
                    raise ShotError("A node connection references an unavailable output socket.")
                wanted = spec[0] if isinstance(spec, list) and spec else None
                actual = outputs[value[1]]
                if (isinstance(wanted, str) and isinstance(actual, str)
                        and not wanted.startswith("COMFY_") and "*" not in (wanted, actual)
                        and not set(wanted.split(",")) & set(actual.split(","))):
                    raise ShotError(f"Connected output type does not match {name}.{key}.")
                continue
            kind = spec[0] if isinstance(spec, list) and spec else None
            settings = spec[1] if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) else {}
            # Model and input asset selectors are checked against the live server list.
            if isinstance(kind, list) and value not in kind:
                raise ShotError(f"Unavailable selection/model/asset: {name}.{key}; check the server selector.")
            if kind == "INT" and type(value) is not int:
                raise ShotError(f"Expected integer input: {name}.{key}.")
            if kind == "FLOAT" and (type(value) not in (int, float)):
                raise ShotError(f"Expected numeric input: {name}.{key}.")
            if kind in ("IMAGE", "AUDIO", "VIDEO", "LATENT", "MODEL", "CLIP", "VAE", "CONDITIONING"):
                raise ShotError(f"Expected a connected input: {name}.{key}.")
            if kind in ("INT", "FLOAT"):
                if value < settings.get("min", value) or value > settings.get("max", value):
                    raise ShotError(f"Input outside installed node limits: {name}.{key}.")
    return {"node_schema_sha256": digest(info), "nodes": len(graph),
            "read_only": True, "model_weight_integrity": "not_verified",
            "gpu_execution": "not_tested"}


def queue_matches(item, state):
    return (isinstance(item, list) and len(item) >= 4 and isinstance(item[3], dict)
            and item[3].get("client_id") == state["client_id"]
            and digest(item[2]) == state["workflow_sha256"])


def find_original(client, state):
    queue = client.json("/queue")
    histories = client.json("/history?max_items=1000")
    matches = set()
    for item in queue.get("queue_running", []) + queue.get("queue_pending", []):
        if queue_matches(item, state):
            matches.add(item[1])
    for prompt_id, item in histories.items():
        if isinstance(item, dict) and queue_matches(item.get("prompt"), state):
            matches.add(prompt_id)
    if len(matches) > 1:
        raise ShotError("Multiple matching original tasks found; inspect history manually. No new submission was sent.")
    return next(iter(matches), None)


def output_record(history, output_node):
    status = history.get("status", {})
    if status.get("status_str") == "error":
        raise ShotError("ComfyUI execution failed; inspect the original task in its UI.")
    if not status.get("completed") or status.get("status_str") != "success":
        raise Pending("Task has not completed successfully; resume this run.")
    # Official SaveVideo -> PreviewVideo.as_dict() exposes the `images` UI key.
    records = history.get("outputs", {}).get(output_node, {}).get("images", [])
    records = [record for record in records if isinstance(record, dict)
               and isinstance(record.get("filename"), str)
               and PurePosixPath(record["filename"]).suffix.lower() in (".mp4", ".webm", ".mkv", ".mov")]
    if len(records) != 1:
        raise ShotError("Successful history lacks exactly one video from the selected SaveVideo node.")
    record = records[0]
    if record.get("type") != "output" or not isinstance(record.get("subfolder", ""), str):
        raise ShotError("SaveVideo returned an unexpected output location.")
    return {key: record.get(key, "") for key in ("filename", "subfolder", "type")}


def download(client, record, destination, max_bytes):
    temporary = destination.with_suffix(".download")
    count = 0
    sha = hashlib.sha256()
    try:
        with client.open("/view?" + urllib.parse.urlencode(record)) as response:
            kind = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if kind not in ("application/octet-stream", "video/mp4", "video/webm", "video/x-matroska", "video/quicktime"):
                raise ShotError("Download returned a non-video content type; no output accepted.")
            raw_length = response.headers.get("Content-Length")
            try:
                expected = int(raw_length) if raw_length else None
            except ValueError:
                raise ShotError("Download has an invalid Content-Length.") from None
            if expected is not None and not 0 < expected <= max_bytes:
                raise ShotError("Download exceeds the configured size limit or is empty.")
            with temporary.open("wb") as stream:
                while True:
                    client.remaining()
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    count += len(block)
                    if count > max_bytes:
                        raise ShotError("Download exceeds the configured size limit.")
                    sha.update(block)
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
            if count == 0 or (expected is not None and count != expected):
                raise Pending("Download is incomplete; resume to fetch the same output again.")
        temporary.replace(destination)
    except (OSError, http.client.HTTPException):
        raise Pending("Output transfer interrupted; resume to fetch the same output again.") from None
    finally:
        temporary.unlink(missing_ok=True)
    return {"file": destination.name, "bytes": count, "sha256": sha.hexdigest()}


def file_hash(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def verify_media(path, expected, client):
    probe_command = ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                     "stream=index,codec_type,width,height,sample_aspect_ratio,avg_frame_rate,nb_read_frames,start_time,duration,sample_rate,channels",
                     "-of", "json", str(path)]
    try:
        probe = subprocess.run(probe_command, capture_output=True, timeout=client.remaining(), check=False)
        if probe.returncode:
            raise ShotError("ffprobe could not completely inspect the output; no media accepted.")
        streams = json.loads(probe.stdout)["streams"]
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if len(videos) != 1 or not audio:
            raise ShotError("Expected one video stream and at least one audio stream.")
        video = videos[0]
        if video.get("sample_aspect_ratio") != "1:1":
            raise ShotError("Video sample aspect ratio must be 1:1; no automatic stretching was applied.")
        actual = {"frames": int(video["nb_read_frames"]), "width": int(video["width"]),
                  "height": int(video["height"])}
        if any(actual[key] != expected[key] for key in actual) or Fraction(video["avg_frame_rate"]) != expected["fps"]:
            raise ShotError("Decoded frame count, dimensions or FPS differ from the locked shot plan.")
        if not all(int(stream.get("nb_read_frames", 0)) > 0 for stream in audio):
            raise ShotError("An audio stream is empty or could not be decoded.")
        packet_probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_packets",
                                       "-show_entries", "packet=stream_index,pts_time,duration_time", "-of", "json", str(path)],
                                      capture_output=True, timeout=client.remaining(), check=False)
        if packet_probe.returncode:
            raise ShotError("Could not inspect actual audio packet timing.")
        packets = json.loads(packet_probe.stdout)["packets"]
        spans = {}
        for packet in packets:
            index = int(packet["stream_index"])
            start = float(packet["pts_time"])
            duration = float(packet["duration_time"])
            if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0:
                raise ShotError("Audio packet timing is invalid or unavailable.")
            previous = spans.get(index, (start, start + duration))
            spans[index] = (min(start, previous[0]), max(start + duration, previous[1]))
        video_start = float(video.get("start_time", 0))
        video_end = video_start + expected["frames"] / expected["fps"]
        if not math.isfinite(video_start):
            raise ShotError("Video start time is invalid.")
        # A small codec delay/padding is normal; a substantially short track is not.
        tolerance = max(0.1, 2 / expected["fps"])
        timing = []
        for stream in audio:
            span = spans.get(int(stream["index"]))
            if span is None or abs(span[0] - video_start) > tolerance or abs(span[1] - video_end) > tolerance:
                raise ShotError("Actual audio start/end do not match the planned video duration within codec tolerance.")
            timing.append({"stream_index": int(stream["index"]), "start_seconds": span[0],
                           "end_seconds": span[1], "duration_seconds": span[1] - span[0]})
        decode = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
                                 "-map", "0:v:0", "-map", "0:a", "-f", "null", "-"],
                                capture_output=True, timeout=client.remaining(), check=False)
        if decode.returncode:
            raise ShotError("Complete video/audio decoding failed; no repair was applied.")
    except subprocess.TimeoutExpired:
        raise Pending("Local inspection reached the time limit; resume to inspect the saved output.") from None
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        raise ShotError("Media metadata is missing or malformed; no output accepted.") from None
    return {**actual, "fps": expected["fps"], "sample_aspect_ratio": "1:1",
            "audio_streams": len(audio), "audio_timing": timing, "audio_timing_tolerance_seconds": tolerance,
            "audio_timing_check": "passed", "full_decode": "passed",
            "visual_review": "pending", "audio_review": "pending"}


@contextmanager
def run_lock(directory):
    # Advisory OS lock is released even when the client process crashes.
    if os.name == "nt":
        import msvcrt
    else:
        import fcntl
    with (directory / ".lock").open("a+b") as stream:
        if os.name == "nt":
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
        try:
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ShotError("Another process is operating on this run directory.") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def run(args, client):
    directory = Path(args.run_dir).expanduser().resolve()
    if directory.exists() and not (directory / "state.json").exists():
        if any(directory.iterdir()):
            raise ShotError("Run directory contains unrelated files; choose a new empty directory.")
    directory.mkdir(parents=True, exist_ok=True)
    with run_lock(directory):
        state_path = directory / "state.json"
        if state_path.exists():
            state = load_json(state_path)
            if state.get("endpoint_sha256") != client.endpoint_sha256:
                raise ShotError("This run belongs to a different ComfyUI endpoint; restore its original environment.")
            graph = load_json(directory / "workflow.api.json")
            if digest(graph) != state.get("workflow_sha256"):
                raise ShotError("Saved workflow fingerprint changed; do not reuse this run directory.")
            if args.workflow and digest(load_json(Path(args.workflow))) != state["workflow_sha256"]:
                raise ShotError("Workflow differs from this run; use a new run directory.")
            for key in ("frames", "fps", "width", "height"):
                if getattr(args, key) is not None and getattr(args, key) != state["expected"][key]:
                    raise ShotError("Expected media parameters differ from this run.")
            if args.output_node is not None and args.output_node != state["output_node"]:
                raise ShotError("Output node differs from this run.")
            if not args.resume and state["phase"] != "checked":
                raise ShotError("This run was already attempted; use --resume. No new submission was sent.")
        else:
            if args.resume:
                raise ShotError("No saved run to resume.")
            if not args.workflow or any(getattr(args, key) is None for key in ("frames", "fps", "width", "height")):
                raise ShotError("New runs require --workflow, --frames, --fps, --width and --height.")
            graph = load_json(Path(args.workflow))
            check_graph(graph, args.output_node or "92")
            state = {"schema_version": 1, "phase": "checked", "client_id": str(uuid.uuid4()),
                     "prompt_id": None, "endpoint_sha256": client.endpoint_sha256,
                     "workflow_sha256": digest(graph), "output_node": args.output_node or "92",
                     "expected": {key: getattr(args, key) for key in ("frames", "fps", "width", "height")},
                     "visual_review": "pending", "audio_review": "pending"}
            save_json(directory / "workflow.api.json", graph)
            save_json(state_path, state)
        try:
            check_graph(graph, state["output_node"])
            check_expected(graph, state["expected"])
            identity = client.identity()
            if state.get("server_identity_sha256") not in (None, identity):
                raise ShotError("Server environment fingerprint changed; inspect the original task manually.")
            state["server_identity_sha256"] = identity
            save_json(state_path, state)
            if state["phase"] == "checked":
                state["preflight"] = preflight(client, graph)
                save_json(state_path, state)
                if args.check or args.resume:
                    return state
                state["phase"] = "submission_unknown"
                save_json(state_path, state)  # Write before POST, including crash/timeout windows.
                reply = client.json("/prompt", {"prompt": graph, "client_id": state["client_id"]})
                prompt_id = reply.get("prompt_id")
                if not isinstance(prompt_id, str) or not prompt_id:
                    raise Pending("Submission reply lacks a PromptID; resume to locate the original task.")
                state["prompt_id"] = prompt_id
                state["phase"] = "queued"
                save_json(state_path, state)
            if state["phase"] == "submission_unknown":
                state["prompt_id"] = find_original(client, state)
                if not state["prompt_id"]:
                    raise Pending("Original submission is absent from queue/recent history. Do not resubmit; inspect the server history.")
                state["phase"] = "queued"
                save_json(state_path, state)
            if state["phase"] == "media_verified":
                if file_hash(directory / state["download"]["file"]) != state["download"]["sha256"]:
                    raise ShotError("Saved media checksum changed; recover the original file before continuing.")
                return state
            while state["phase"] == "queued":
                prompt_id = state["prompt_id"]
                histories = client.json("/history/" + urllib.parse.quote(prompt_id, safe=""))
                history = histories.get(prompt_id)
                if history:
                    if "prompt" in history and not queue_matches(history["prompt"], state):
                        raise ShotError("History belongs to a different client or workflow; no output accepted.")
                    state["output_record"] = output_record(history, state["output_node"])
                    state["phase"] = "generated"
                    save_json(state_path, state)
                    break
                queue = client.json("/queue")
                present = any(isinstance(item, list) and len(item) > 1 and item[1] == prompt_id
                              for item in queue.get("queue_running", []) + queue.get("queue_pending", []))
                if not present:
                    raise Pending("PromptID is absent from queue/history; retain this run and inspect the original server.")
                time.sleep(min(3, client.remaining()))
            if state["phase"] == "generated":
                extension = PurePosixPath(state["output_record"]["filename"]).suffix.lower()
                state["download"] = download(client, state["output_record"], directory / ("video" + extension),
                                             args.max_download_mib * 1024 * 1024)
                state["phase"] = "downloaded"
                save_json(state_path, state)
            if state["phase"] == "downloaded":
                path = directory / state["download"]["file"]
                if file_hash(path) != state["download"]["sha256"]:
                    raise ShotError("Saved media checksum changed; recover the original file before continuing.")
                state["verification"] = verify_media(path, state["expected"], client)
                state["phase"] = "media_verified"
                state.pop("last_diagnostic", None)
                save_json(state_path, state)
            return state
        except (Pending, ShotError) as error:
            state["last_diagnostic"] = str(error)
            save_json(state_path, state)
            raise


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    action = result.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Read-only remote preflight; never submit")
    action.add_argument("--execute", action="store_true", help="Submit once after successful preflight")
    action.add_argument("--resume", action="store_true", help="Recover an existing run; never submit")
    result.add_argument("--workflow", help="Rendered ComfyUI API JSON")
    result.add_argument("--run-dir", required=True, help="One persistent directory per shot attempt")
    for key in ("frames", "fps", "width", "height"):
        result.add_argument("--" + key, type=positive)
    result.add_argument("--output-node", help="SaveVideo node ID (new-run default: 92)")
    result.add_argument("--max-download-mib", type=positive, default=2048)
    result.add_argument("--wait-seconds", type=positive, default=60, help="Per-invocation budget, maximum 60")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.wait_seconds > 60:
        parser().error("--wait-seconds must not exceed 60")
    try:
        if not all(shutil.which(tool) for tool in ("ffprobe", "ffmpeg")):
            raise ShotError("Install ffprobe and ffmpeg and verify they are on PATH before running.")
        client = Client(os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188"),
                        args.wait_seconds, os.environ.get("COMFY_AUTH_TOKEN"))
        state = run(args, client)
        print(json.dumps({"phase": state["phase"], "prompt_id": state["prompt_id"],
                          "visual_review": "pending", "audio_review": "pending"}))
        return 0
    except Pending as error:
        print("PENDING: " + str(error), file=sys.stderr)
        return 3
    except ShotError as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print("ERROR: Local state or I/O is invalid. Inspect the run directory; no automatic resubmission.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
