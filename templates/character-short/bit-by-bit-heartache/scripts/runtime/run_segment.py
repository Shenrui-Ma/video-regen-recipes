#!/usr/bin/env python3
"""Portable Heartache single-segment runner; stdlib only. Submission is opt-in."""
import argparse
from contextlib import contextmanager
import errno
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

VERSION = "1.1.0"
TOKEN = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


def bind_graph(template, bindings):
    """Only whole-value placeholders are supported; never eval input."""
    if not isinstance(template, dict) or not isinstance(bindings, dict):
        raise ValueError("graph and bindings must be objects")

    def walk(value, key="", substitute=True):
        if isinstance(value, str):
            match = TOKEN.fullmatch(value)
            if match and substitute:
                name = match[1]
                if name not in bindings:
                    raise ValueError("missing binding")
                return walk(bindings[name], key, False)
            if "{{" in value or "}}" in value:
                raise ValueError("unknown or embedded placeholder")
        if "seed" in key.lower() and type(value) is not int:
            raise ValueError("seed must be an integer, not bool")
        if key == "metadata_json" and not isinstance(value, str):
            raise ValueError("metadata_json must remain a JSON string")
        if isinstance(value, dict):
            if any("{{" in k or "}}" in k for k in value):
                raise ValueError("placeholder keys are unsupported")
            return {k: walk(v, k, substitute) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, "", substitute) for v in value]
        return value
    return walk(template)


class RunnerError(Exception):
    pass


class SubmitHTTPError(RunnerError):
    """Keep untrusted response data out of the exception's printable message."""
    def __init__(self, status, body):
        super().__init__("HTTP_SUBMIT_ERROR")
        self.status = status
        self.body = body


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, host, timeout, interval):
        parts = urllib.parse.urlsplit(host)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment
                or parts.path not in ("", "/")):
            raise ValueError("host must be an HTTP origin without credentials")
        self.host, self.timeout, self.interval = host.rstrip("/"), timeout, interval
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, path, body=None):
        method = "GET" if body is None else "POST"
        for attempt in range(3 if method == "GET" else 1):
            try:
                data = None if body is None else json.dumps(body, allow_nan=False).encode()
                req = urllib.request.Request(self.host + path, data=data,
                                             headers={"Content-Type": "application/json"}, method=method)
                with self.opener.open(req, timeout=self.timeout) as response:
                    result = json.load(response)
                if not isinstance(result, dict):
                    raise ValueError("non-object response")
                return result
            except urllib.error.HTTPError as error:
                with error:
                    if method == "POST":
                        try:
                            result = json.load(error)
                        except (OSError, ValueError, http.client.HTTPException):
                            raise RunnerError("HTTP_IO_FAILED") from None
                        raise SubmitHTTPError(error.code, result) from None
                if attempt == 2:
                    raise RunnerError("HTTP_IO_FAILED") from None
            except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
                if method == "POST" or attempt == 2:
                    raise RunnerError("HTTP_IO_FAILED") from None
            time.sleep(min(self.interval, 1))


def queue_ids(queue):
    ids = []
    for key in ("queue_running", "queue_pending"):
        rows = queue.get(key)
        if not isinstance(rows, list):
            raise RunnerError("INVALID_QUEUE")
        for row in rows:
            if not isinstance(row, list) or len(row) < 2 or not isinstance(row[1], str):
                raise RunnerError("INVALID_QUEUE")
            ids.append(row[1])
    return ids


def preflight(api, graph):
    info = api.request("/object_info")
    if not graph or any(not isinstance(node, dict) or
                        node.get("class_type") not in info for node in graph.values()):
        raise RunnerError("MISSING_NODE_CLASS")
    if queue_ids(api.request("/queue")):
        raise RunnerError("QUEUE_BUSY")



@contextmanager
def state_lock(path):
    """Nonblocking OS lock; retain the file so contenders share one inode."""
    with open(path, "a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        elif os.name == "posix":
            import fcntl
            acquire = lambda: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(lock, fcntl.LOCK_UN)
        else:
            raise RunnerError("UNSUPPORTED_PLATFORM")
        try:
            acquire()
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise RunnerError("STATE_LOCKED") from None
            raise
        try:
            yield
        finally:
            lock.seek(0)
            release()


def atomic_json(path, value):
    """Same-directory replace, file fsync, and POSIX directory fsync.

    Windows has no stdlib directory-fsync equivalent; close before replace.
    """
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        if os.name == "posix":
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def outcome(state):
    return {k: state[k] for k in ("status", "prompt_id", "client_id", "graph_sha256",
                                  "runner_version", "outputs") if k in state}


def is_rejection(archive):
    body = archive.get("body") if isinstance(archive, dict) else None
    return (isinstance(body, dict) and archive.get("http_status") == 400
            and bool(body.get("error")) and not body.get("prompt_id"))


def follow(api, directory, state):
    pid = state["prompt_id"]
    route = "/history/" + urllib.parse.quote(pid, safe="")
    while True:
        try:
            history = api.request(route)
            row = history.get(pid)
            if not row:
                queued = pid in queue_ids(api.request("/queue"))
                # Re-read once to close the queue-to-history handoff race.
                if not queued:
                    history = api.request(route)
                    row = history.get(pid)
                    if not row:
                        state["status"] = "AMBIGUOUS"
                        break
            if row:
                atomic_json(directory / "history.json", history)
                status = row.get("status", {})
                messages = status.get("messages", [])
                failed = status.get("status_str") == "error" or any(
                    isinstance(m, list) and m and m[0] in
                    ("execution_error", "execution_interrupted") for m in messages)
                if failed:
                    state["status"] = "FAILED"
                    break
                if status.get("completed") is True and status.get("status_str") == "success":
                    state["status"] = "SUCCESS"
                    state["outputs"] = row.get("outputs", {})
                    break
                # Nonterminal history without a queue entry cannot prove liveness.
                if pid not in queue_ids(api.request("/queue")):
                    state["status"] = "AMBIGUOUS"
                    break
            time.sleep(api.interval)
        except (RunnerError, AttributeError, TypeError, ValueError):
            state["status"] = "AMBIGUOUS"
            break
    atomic_json(directory / "state.json", state)
    return outcome(state), 0 if state["status"] == "SUCCESS" else 1


def run(api, graph, directory, check_only):
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    state_path = directory / "state.json"

    def existing():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state["graph_sha256"] != digest or state["host"] != api.host
                or str(uuid.UUID(state["prompt_id"])) != state["prompt_id"]
                or str(uuid.UUID(state["client_id"])) != state["client_id"]):
            raise RunnerError("STATE_MISMATCH")
        return state

    if check_only:
        if state_path.exists():
            state = existing()
            api.request("/history/" + state["prompt_id"])
            queue_ids(api.request("/queue"))
        else:
            preflight(api, graph)
        return {"status": "CHECKED", "runner_version": VERSION}, 0

    directory.mkdir(parents=True, exist_ok=True)
    with state_lock(directory / ".lock"):
        if state_path.exists():
            state = existing()
            if state["status"] in ("SUCCESS", "FAILED", "REJECTED"):
                return outcome(state), 0 if state["status"] == "SUCCESS" else 1
            response_path = directory / "submit-response.json"
            # v1.0 wrote raw success bodies, not the local response envelope.
            if state.get("runner_version") == VERSION and response_path.exists():
                archive = json.loads(response_path.read_text(encoding="utf-8"))
                if is_rejection(archive):
                    state["status"] = "REJECTED"
                    atomic_json(state_path, state)
                    return outcome(state), 1
            return follow(api, directory, state)
        preflight(api, graph)
        state = {"runner_version": VERSION, "host": api.host,
                 "client_id": str(uuid.uuid4()), "prompt_id": str(uuid.uuid4()),
                 "graph_sha256": digest, "status": "SUBMIT_INTENT"}
        atomic_json(directory / "graph.json", graph)
        atomic_json(state_path, state)
        try:
            reply = api.request("/prompt", {"prompt": graph,
                                "client_id": state["client_id"], "prompt_id": state["prompt_id"]})
            atomic_json(directory / "submit-response.json", {"body": reply})
            # A differing ID cannot authorize following a different job.
        except SubmitHTTPError as error:
            archive = {"http_status": error.status, "body": error.body}
            atomic_json(directory / "submit-response.json", archive)
            if is_rejection(archive):
                state["status"] = "REJECTED"
                atomic_json(state_path, state)
                return outcome(state), 1
        except RunnerError:
            pass  # A lost response is not permission to POST again.
        return follow(api, directory, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("host", "graph", "bindings", "state-dir"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Explicitly authorize GPU submission")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        if any(not math.isfinite(v) or v <= 0 for v in (args.interval, args.timeout)):
            raise ValueError("positive finite timing required")
        graph = bind_graph(json.loads(Path(args.graph).read_text(encoding="utf-8")),
                           json.loads(Path(args.bindings).read_text(encoding="utf-8")))
        api = API(args.host, args.timeout, args.interval)
        result, code = run(api, graph, Path(args.state_dir), args.check_only or not args.execute)
    except KeyboardInterrupt:
        result, code = {"status": "AMBIGUOUS"}, 130
    except RunnerError as error:
        result, code = {"status": str(error)}, 1
    except (OSError, ValueError, TypeError, KeyError):
        result, code = {"status": "INVALID_INPUT_OR_STATE"}, 1
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
