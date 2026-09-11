#!/usr/bin/env python3
"""Validate local episode assets and export H3 API graphs. Never submits jobs."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys


TEMPLATE = Path(__file__).resolve().parents[1] / "workflows/ref2va.api.template.json"
ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
SHOT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}\Z")
SHA = re.compile(r"[a-f0-9]{64}\Z")
PLACEHOLDER = re.compile(r"\{\{|\}\}|\b(?:TODO|TBD|REPLACE(?:_[A-Z0-9_]+)?|YOUR_[A-Z_]+)\b|<[^>]*(?:PATH|KEY|TOKEN)[^>]*>", re.I)
ROLE = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*)")
LANGUAGES = {"Japanese", "English", "Chinese"}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as error:
        raise Invalid(f"Cannot read valid JSON: {Path(path).name}") from error


def fields(value, required, optional, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) >= set(required), f"{label}: missing fields {sorted(set(required) - set(value))}")
    require(set(value) <= set(required) | set(optional), f"{label}: unknown fields {sorted(set(value) - set(required) - set(optional))}")


def text(value, label):
    require(isinstance(value, str) and value.strip(), f"{label} must be nonempty text")
    require(not PLACEHOLDER.search(value), f"{label} contains an unfilled placeholder")
    require("\x00" not in value, f"{label} contains a NUL byte")
    return value.strip()


def relative_name(value, label):
    value = text(value, label)
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in value,
            f"{label} must be a relative path without '..' or backslashes")
    require(not re.match(r"^[A-Za-z]:", value) and not re.search(r"\[(?:input|output|temp)\]$", value),
            f"{label} must be an input-relative filename, without path annotations")
    require(not any(c in value for c in ("\n", "\r", "\t")) and "://" not in value and value != ".",
            f"{label} is not a relative filename")
    return path.as_posix()


def integer(value, label, minimum=1, maximum=None):
    require(type(value) is int and value >= minimum and (maximum is None or value <= maximum),
            f"{label} must be an integer in the allowed range")
    return value


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_media(path):
    require(shutil.which("ffprobe") is not None, "ffprobe is required; install FFmpeg and retry")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as error:
        raise Invalid(f"ffprobe could not inspect asset: {path.name}") from error


def inspect_asset(root, filename, kind, cache):
    name = relative_name(filename, f"{kind} asset")
    if (name, kind) in cache:
        return cache[(name, kind)]
    path = (root / name).resolve()
    require(path.is_relative_to(root), f"Asset escapes the episode directory: {name}")
    require(path.is_file() and path.stat().st_size > 0, f"Missing or empty asset: {name}")
    if kind == "image":
        require(path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}, f"Unsupported image extension: {name}")
    else:
        require(path.suffix.lower() == ".wav", f"Voice reference must be a WAV: {name}")
    before = file_sha(path)
    media = probe_media(path)
    streams = media.get("streams", [])
    record = {"path": name, "sha256": before, "kind": kind}
    if kind == "image":
        video = [stream for stream in streams if stream.get("codec_type") == "video"]
        require(len(video) == 1 and video[0].get("width", 0) > 0 and video[0].get("height", 0) > 0,
                f"Image has no readable dimensions: {name}")
        require(video[0].get("nb_frames") in (None, "N/A", "1", 1), f"Use a still image, not an animation: {name}")
        record.update(width=video[0]["width"], height=video[0]["height"])
    else:
        audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
        require(len(streams) == len(audio) == 1, f"Voice WAV must contain one audio stream only: {name}")
        require(audio[0].get("codec_name", "").startswith("pcm_"), f"Voice WAV must contain uncompressed PCM: {name}")
        try:
            duration = float(audio[0].get("duration", media.get("format", {}).get("duration")))
            rate = int(audio[0].get("sample_rate", 0))
        except (ValueError, TypeError) as error:
            raise Invalid(f"Voice duration/sample rate unavailable: {name}") from error
        require(math.isfinite(duration) and 2 <= duration <= 15, f"Voice duration must be 2–15 seconds: {name}")
        require(rate > 0 and audio[0].get("channels") in (1, 2), f"Voice must have a valid rate and 1 or 2 channels: {name}")
        record.update(duration_seconds=duration, sample_rate=rate, channels=audio[0]["channels"])
    require(file_sha(path) == before, f"Asset changed while being inspected: {name}")
    cache[(name, kind)] = record
    return record


def replace_roles(value, cast, label):
    value = text(value, label)
    require(not re.search(r"<(?:Subject|Picture|Audio)\s+\d+>", value, re.I),
            f"{label}: use @character_id instead of hand-written reference numbers")
    def replace(match):
        require(match[1] in cast, f"{label}: @{match[1]} is not in this shot's cast")
        return f"<Subject {cast.index(match[1]) + 1}>"
    result = ROLE.sub(replace, value)
    require("@" not in result, f"{label}: malformed @character_id")
    return result


def validate_episode(episode, root, allow_missing_turnarounds=False, selected_shots=None):
    fields(episode, ["schema_version", "title", "franchise", "fps", "width", "height", "steps", "model_files", "characters", "scenes", "shots"], ["dialogue_language"], "episode")
    require(type(episode["schema_version"]) is int and episode["schema_version"] == 1, "schema_version must be 1")
    for key in ("title", "franchise"):
        text(episode[key], key)
    require(isinstance(episode.get("dialogue_language", "Japanese"), str) and episode.get("dialogue_language", "Japanese") in LANGUAGES,
            "dialogue_language must be Japanese, English or Chinese")
    require(type(episode["fps"]) is int and episode["fps"] == 24, "This recipe uses 24 fps")
    require(type(episode["steps"]) is int and episode["steps"] == 20, "This baseline uses 20 steps; benchmark acceleration in a separate recipe")
    for key in ("width", "height"):
        require(integer(episode[key], key, 32) % 32 == 0, f"{key} must be a multiple of 32")
    fields(episode["model_files"], ["diffusion_model", "text_encoder", "video_vae", "audio_vae"], [], "model_files")
    for key, value in episode["model_files"].items():
        relative_name(value, f"model_files.{key}")
    characters, scenes, shots = episode["characters"], episode["scenes"], episode["shots"]
    require(isinstance(characters, dict) and characters, "characters must be a nonempty object")
    require(isinstance(scenes, dict) and scenes, "scenes must be a nonempty object")
    require(isinstance(shots, list) and shots, "shots must be a nonempty list")
    for cid, character in characters.items():
        require(ID.fullmatch(cid), f"Invalid character id: {cid}")
        require(isinstance(character, dict), f"characters.{cid} must be an object")
    for sid, scene in scenes.items():
        require(ID.fullmatch(sid), f"Invalid scene id: {sid}")
        require(isinstance(scene, dict), f"scenes.{sid} must be an object")
    all_ids = []
    for shot in shots:
        require(isinstance(shot, dict) and isinstance(shot.get("id"), str) and SHOT_ID.fullmatch(shot["id"]),
                "Every shot needs a lowercase alphanumeric id")
        all_ids.append(shot["id"])
    require(len(all_ids) == len(set(all_ids)), "Shot ids must be unique")
    if selected_shots is not None:
        require(selected_shots and all(sid in all_ids for sid in selected_shots), "--shot contains an unknown shot id")
        require(len(selected_shots) == len(set(selected_shots)), "Do not repeat the same --shot id")
        shots = [shot for shot in shots if shot["id"] in selected_shots]
    cache, result, ids = {}, [], set()
    for shot in shots:
        fields(shot, ["id", "scene", "cast", "frames", "seed", "visual_description", "dialogue", "ambience"], [], "shot")
        sid = shot["id"]
        require(isinstance(sid, str) and SHOT_ID.fullmatch(sid) and sid not in ids, "Shot ids must be unique lowercase identifiers")
        ids.add(sid)
        require(isinstance(shot["scene"], str) and shot["scene"] in scenes, f"{sid}: unknown scene")
        scene = scenes[shot["scene"]]
        fields(scene, ["description", "image"], [], f"{sid}.scene")
        for key in ("description", "image"):
            text(scene[key], f"{sid}.scene.{key}")
        cast = shot["cast"]
        require(isinstance(cast, list) and cast and all(isinstance(c, str) for c in cast), f"{sid}: cast must be a nonempty list of ids")
        require(len(cast) == len(set(cast)) and all(cid in characters for cid in cast), f"{sid}: duplicate/unknown cast")
        for cid in cast:
            character = characters[cid]
            fields(character, ["name", "appearance", "identity_image"], ["turnaround_image", "voice_audio"], f"characters.{cid}")
            for key in ("name", "appearance", "identity_image"):
                text(character[key], f"characters.{cid}.{key}")
        frames = integer(shot["frames"], f"{sid}.frames", 22)
        require((frames - 5) % 17 == 0, f"{sid}: frames must follow 17*k+5, for example 175, 226, 243")
        integer(shot["seed"], f"{sid}.seed", 0, 2**64 - 1)
        visual = replace_roles(shot["visual_description"], cast, f"{sid}.visual_description")
        ambience = replace_roles(shot["ambience"], cast, f"{sid}.ambience")
        require(isinstance(shot["dialogue"], list) and shot["dialogue"], f"{sid}: dialogue must include at least one speaker")
        speakers = []
        for line in shot["dialogue"]:
            fields(line, ["character", "text", "delivery"], [], f"{sid}.dialogue")
            cid = line["character"]
            require(isinstance(cid, str) and cid in cast, f"{sid}: dialogue speaker must belong to cast")
            words = text(line["text"], f"{sid}.dialogue.text")
            require(not re.search(r"[<>\r\n]|\[(?:Shot\b|Audio\b|Subject\b|Japanese\b|English\b|Chinese\b)|\(S\d+\)", words, re.I),
                    f"{sid}: dialogue.text must be plain spoken text, without H3/language/speaker tags")
            replace_roles(line["delivery"], cast, f"{sid}.dialogue.delivery")
            if cid not in speakers:
                speakers.append(cid)
        require(len(speakers) <= 3, f"{sid}: at most 3 voice references per clip")
        images, voices, omitted = [], [], []
        for cid in cast:
            asset = inspect_asset(root, characters[cid]["identity_image"], "image", cache)
            images.append({**asset, "role": "identity", "character": cid})
        for cid in speakers:
            filename = characters[cid].get("turnaround_image")
            if filename:
                images.append({**inspect_asset(root, filename, "image", cache), "role": "turnaround", "character": cid})
            else:
                require(allow_missing_turnarounds, f"{sid}: {cid} has no turnaround; provide it or explicitly use --allow-missing-turnarounds")
                omitted.append(cid)
            require(characters[cid].get("voice_audio"), f"{sid}: {cid} has no voice_audio")
            voices.append({**inspect_asset(root, characters[cid]["voice_audio"], "audio", cache), "character": cid})
        images.append({**inspect_asset(root, scenes[shot["scene"]]["image"], "image", cache), "role": "scene", "scene": shot["scene"]})
        require(len(images) <= 8, f"{sid}: this baseline supports at most 8 images; reduce cast/turnarounds before using a new input regime")
        require(sum(voice["duration_seconds"] for voice in voices) <= 15.000001, f"{sid}: combined voice references exceed 15 seconds")
        result.append({"shot": shot, "speakers": speakers, "images": images, "voices": voices,
                       "omitted_turnarounds": omitted, "visual": visual, "ambience": ambience})
    return result


def build_prompt(episode, item):
    shot, images = item["shot"], item["images"]
    cast, speakers = shot["cast"], item["speakers"]
    definitions, retention = [], []
    turnarounds = {asset["character"]: index for index, asset in enumerate(images, 1) if asset["role"] == "turnaround"}
    for index, cid in enumerate(cast, 1):
        character = episode["characters"][cid]
        definition = f"<Subject {index}> is {character['name']}. Identity and fixed outfit: <Picture {index}>. {character['appearance']}"
        if cid in turnarounds:
            definition += f" Additional appearance reference: <Picture {turnarounds[cid]}> shows multiple views of this SAME person, never extra people."
        definitions.append(definition)
        retention.append(f"<Subject {index}>: fully_preserved - retain identity, face, hair, fixed costume and body proportions; generate new expressions and actions.")
    definitions.append(f"<Subject {len(cast) + 1}> is the set in <Picture {len(images)}>: {episode['scenes'][shot['scene']]['description']}. It is a soft environment/composition reference, not a locked first frame. People visible there are the same cast, never additional people.")
    retention.append(f"<Subject {len(cast) + 1}>: weak_reference - use set layout, prop positions, palette and lighting as guidance; adapt framing and composition to the requested shot.")
    for index, cid in enumerate(speakers, 1):
        subject = cast.index(cid) + 1
        definitions.append(f"<Audio {index}> provides the voice timbre of <Subject {subject}> (S{index}) only. Generate new dialogue; do not copy its original words, timing, emotion or background sounds.")
        retention.append(f"<Audio {index}>: reference - retain the assigned character's voice timbre for new dialogue; do not copy source words, cadence, emotion or background sound.")
    dialogue = []
    for line in shot["dialogue"]:
        cid = line["character"]
        delivery = replace_roles(line["delivery"], cast, "dialogue.delivery")
        speaker_number = speakers.index(cid) + 1
        language = episode.get("dialogue_language", "Japanese")
        dialogue.append(f"<Subject {cast.index(cid) + 1}> (S{speaker_number}) speaks using the voice of <Audio {speaker_number}>. Delivery: {delivery}. <d>[{language}] {line['text']}</d>")
    return "\n\n".join([
        "subject_definitions:\n" + "\n".join(definitions),
        f"summary:\n[reference generation + audio reference] Anime dialogue scene for {episode['franchise']}. One independent clip, {shot['frames']} visible frames at 24 fps ({shot['frames'] / 24:.9f} seconds).",
        "retention_analysis:\n" + "\n".join(retention),
        "detailed_description:\nAnime visual style with consistent character design and restrained, readable acting.\n[Shot 1] " + item["visual"] + "\nDialogue in order, without overlap:\n" + "\n".join(dialogue) + "\nOnly the current speaker moves their mouth for dialogue. Preserve relative positions and action direction; show a motivated entrance before introducing a new visible character. Finish the last line naturally within the clip.",
        "overall_soundscape:\n" + item["ambience"] + " Clear diegetic dialogue takes priority over ambience.",
        "non_diegetic_music:\nN/A",
    ]) + "\n"


def validate_bindings(bindings):
    fields(bindings, ["schema_version", "files"], [], "bindings")
    require(type(bindings["schema_version"]) is int and bindings["schema_version"] == 1, "bindings.schema_version must be 1")
    require(isinstance(bindings["files"], dict), "bindings.files must be an object keyed by local SHA-256")
    names = {}
    for digest, entry in bindings["files"].items():
        require(SHA.fullmatch(digest), "Every bindings.files key must be a lowercase SHA-256")
        fields(entry, ["name", "sha256"], [], "binding")
        require(entry["sha256"] == digest, "Binding key and verified SHA-256 disagree")
        name = relative_name(entry["name"], "binding.name")
        require(name not in names or names[name] == digest, "Two different files cannot share one ComfyUI input name")
        names[name] = digest
    return bindings["files"]


def make_graph(episode, item, bindings, prefix):
    shot = item["shot"]
    prompt = build_prompt(episode, item)
    values = {**episode["model_files"], "steps": episode["steps"], "width": episode["width"], "height": episode["height"],
              "frames": shot["frames"], "seed": shot["seed"], "prompt": prompt, "filename_prefix": prefix}
    def render(value):
        if isinstance(value, dict):
            return {key: render(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [render(nested) for nested in value]
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            require(value[2:-2] in values, f"Unknown API template variable: {value}")
            return values[value[2:-2]]
        return value
    graph = render(read_json(TEMPLATE))
    for kind, assets, node_start, field in [("image", item["images"], 200, "ref_images.ref_image"), ("audio", item["voices"], 220, "ref_audios.ref_audio")]:
        for index, asset in enumerate(assets):
            require(asset["sha256"] in bindings, f"No verified ComfyUI input binding for {asset['path']}")
            name = relative_name(bindings[asset["sha256"]]["name"], "binding.name")
            nid = str(node_start + index)
            graph[nid] = {"class_type": "LoadImage" if kind == "image" else "LoadAudio", "inputs": {kind: name}}
            graph["136"]["inputs"][f"{field}_{index}"] = [nid, 0]
    return graph, prompt


def export_episode(episode_path, bindings_path, output, allow_missing_turnarounds=False, selected_shots=None):
    episode_path, output = Path(episode_path).resolve(), Path(output).resolve()
    require(not output.exists(), "Output already exists; choose a new version directory")
    episode = read_json(episode_path)
    items = validate_episode(episode, episode_path.parent, allow_missing_turnarounds, selected_shots)
    bindings = validate_bindings(read_json(bindings_path))
    run_id = hashlib.sha256(json.dumps(episode, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    safe_version = re.sub(r"[^A-Za-z0-9_-]+", "-", output.name).strip("-") or "version"
    manifest = {"schema_version": 1, "status": "built-not-submitted", "title": episode["title"], "franchise": episode["franchise"],
                "dialogue_language": episode.get("dialogue_language", "Japanese"),
                "fps": 24, "width": episode["width"], "height": episode["height"], "steps": 20,
                "mode": "independent-ref2va", "selected_shots": [item["shot"]["id"] for item in items],
                "total_expected_frames": sum(item["shot"]["frames"] for item in items),
                "model_files": copy.deepcopy(episode["model_files"]), "shots": []}
    artifacts = {}
    for item in items:
        sid = item["shot"]["id"]
        graph, prompt = make_graph(episode, item, bindings, f"video-regen/{safe_version}-{run_id}/{sid}")
        graph_bytes = (json.dumps(graph, ensure_ascii=False, indent=2) + "\n").encode()
        artifacts[f"api/{sid}.json"] = graph_bytes
        artifacts[f"prompts/{sid}.txt"] = prompt.encode()
        manifest["shots"].append({"id": sid, "seed": item["shot"]["seed"], "expected_frames": item["shot"]["frames"],
            "expected_seconds": item["shot"]["frames"] / 24, "api_graph": f"api/{sid}.json", "prompt": f"prompts/{sid}.txt",
            "api_sha256": hashlib.sha256(graph_bytes).hexdigest(), "cast_order": item["shot"]["cast"], "speaker_order": item["speakers"],
            "images": [{**asset, "comfyui_name": bindings[asset["sha256"]]["name"]} for asset in item["images"]],
            "voices": [{**asset, "comfyui_name": bindings[asset["sha256"]]["name"]} for asset in item["voices"]],
            "omitted_turnarounds": item["omitted_turnarounds"]})
    artifacts["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    # Claim the directory exclusively only after every validation and render succeeds.
    output.mkdir(parents=True, exist_ok=False)
    marker = output / ".incomplete"
    marker.write_text("Export is incomplete until this marker disappears.\n", encoding="utf-8")
    for name, content in artifacts.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(content)
    marker.unlink()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--check-local", action="store_true", help="Validate local files only; no bindings or output")
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-missing-turnarounds", action="store_true")
    parser.add_argument("--shot", action="append", dest="selected_shots", help="Check/build only this shot id; repeat to select more")
    args = parser.parse_args()
    try:
        if args.check_local:
            require(args.bindings is None and args.output is None, "--check-local cannot be combined with --bindings/--output")
            path = args.episode.resolve()
            episode = read_json(path)
            items = validate_episode(episode, path.parent, args.allow_missing_turnarounds, args.selected_shots)
            result = {"status": "local-assets-checked-not-uploaded", "shots": len(items),
                      "total_expected_frames": sum(item["shot"]["frames"] for item in items)}
        else:
            require(args.bindings is not None and args.output is not None, "Building requires both --bindings and --output")
            manifest = export_episode(args.episode, args.bindings, args.output, args.allow_missing_turnarounds, args.selected_shots)
            result = {"status": manifest["status"], "shots": len(manifest["shots"]), "total_expected_frames": manifest["total_expected_frames"]}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Invalid, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
