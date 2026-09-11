#!/usr/bin/env python3
"""Validate selected local clips; opt in to a new FFV1/PCM episode master."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile


SAMPLE_RATE = 48000
FPS = 24
AUDIO_TOLERANCE_SAMPLES = 4800


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    def unique_pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, json.JSONDecodeError) as error:
        raise Invalid("Cannot read selected-segments.json") from error


def run(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as error:
        raise Invalid(f"{Path(args[0]).name} could not complete") from error
    require(result.returncode == 0 and not result.stderr.strip(),
            f"{Path(args[0]).name} reported an error: {result.stderr[-1500:]}")
    return result.stdout


def probe(path):
    try:
        return json.loads(run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                               "-show_format", "-of", "json", str(path)]))
    except json.JSONDecodeError as error:
        raise Invalid("ffprobe did not return JSON") from error


def audio_samples(path):
    """Count decoded 48 kHz stereo samples without holding the soundtrack in RAM."""
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
                 "-map", "0:a:0", "-vn", "-ar", str(SAMPLE_RATE), "-ac", "2",
                 "-c:a", "pcm_s24le", "-f", "s24le", "-"],
                stdout=subprocess.PIPE, stderr=errors,
            )
            count = 0
            try:
                for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                    count += len(block)
                code = process.wait(timeout=3600)
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
            errors.seek(0)
            diagnostic = errors.read().decode("utf-8", errors="replace")
        except (OSError, subprocess.SubprocessError) as error:
            raise Invalid("Could not decode the audio track") from error
    require(code == 0 and not diagnostic.strip(), "Audio decoding failed")
    require(count > 0 and count % 6 == 0, "Audio track has no complete stereo samples")
    return count // 6


def inspect(path, expected, *, exact_audio=False):
    data = probe(path)
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    audios = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    require(len(videos) == 1 and len(audios) == 1, "Each clip needs exactly one video and one audio track")
    video, audio = videos[0], audios[0]
    if exact_audio:
        require(audio.get("sample_rate") == str(SAMPLE_RATE) and audio.get("channels") == 2,
                "Master audio must be 48 kHz stereo")
    require((video.get("width"), video.get("height")) == (expected["width"], expected["height"]),
            "Video dimensions do not match the selected-segments plan")
    require(video.get("sample_aspect_ratio") == "1:1", "Video SAR must already be 1:1")
    try:
        require(Fraction(video["avg_frame_rate"]) == FPS, "Video must already be 24 fps")
        require(int(video["nb_read_frames"]) == expected["frames"], "Decoded frame count does not match the plan")
        start_delta = abs(float(audio.get("start_time", 0)) - float(video.get("start_time", 0)))
        require(start_delta <= 0.1 + 1e-9, "Audio/video start offset exceeds 0.1 seconds")
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        if isinstance(error, Invalid):
            raise
        raise Invalid("Cannot verify frame count, rate, or audio/video start time") from error
    # Average FPS alone can hide variable-frame-rate input. Check the actual grid.
    frame_data = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path)]))
    try:
        times = [float(f["best_effort_timestamp_time"]) for f in frame_data["frames"]]
        require(len(times) == expected["frames"], "Missing decoded frame timestamps")
        require(all(abs(t - times[0] - i / FPS) <= 0.0011 for i, t in enumerate(times)),
                "Video timestamps are not on a 24 fps grid; refusing to retime")
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, Invalid):
            raise
        raise Invalid("Cannot verify decoded frame timestamps") from error
    samples = audio_samples(path)
    target = expected["frames"] * (SAMPLE_RATE // FPS)
    tolerance = 0 if exact_audio else AUDIO_TOLERANCE_SAMPLES
    require(abs(samples - target) <= tolerance,
            "Audio length differs from the video plan by more than the allowed boundary tolerance")
    return {"frames": expected["frames"], "audio_samples": samples,
            "target_audio_samples": target, "audio_adjustment_samples": target - samples,
            "pixel_format": video.get("pix_fmt"), "audio_video_start_delta_seconds": start_delta,
            "video_codec": video.get("codec_name"), "audio_codec": audio.get("codec_name")}


def validate(manifest_path, project_root, output):
    require(shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None,
            "ffmpeg and ffprobe must be available on PATH")
    manifest_path, project_root, output = manifest_path.resolve(), project_root.resolve(), output.resolve()
    require(manifest_path.is_relative_to(project_root), "The selected-segments file must be inside the project root")
    require(output.is_relative_to(project_root) and output != project_root,
            "Output must be a new directory inside the project root")
    require(not output.exists(), "Output directory already exists; choose a new version")
    data = read_json(manifest_path)
    required = {"fps", "width", "height", "segments"}
    require(isinstance(data, dict) and required <= set(data) <= required | {"schema_version"},
            "Use selected-segments.json with fps/width/height/segments, not the episode story plan")
    require(type(data["fps"]) is int and data["fps"] == FPS, "This assembler supports fps=24 only")
    for key in ("width", "height"):
        require(type(data[key]) is int and data[key] > 0, f"{key} must be a positive integer")
    require(isinstance(data["segments"], list) and data["segments"], "segments must be a nonempty ordered list")
    if "schema_version" in data:
        require(type(data["schema_version"]) is int and data["schema_version"] == 1, "Unsupported schema_version")
    seen_ids, seen_paths, accepted = set(), set(), []
    for item in data["segments"]:
        fields = {"id", "path", "sha256", "frames", "visual_review", "audio_review"}
        require(isinstance(item, dict) and set(item) == fields, "Each selected segment must have exactly the documented fields")
        sid = item["id"]
        require(isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", sid), "Invalid segment id")
        require(sid not in seen_ids, "Duplicate segment id")
        seen_ids.add(sid)
        require(item["visual_review"] == item["audio_review"] == "accepted", f"{sid}: both reviews must be accepted")
        require(type(item["frames"]) is int and item["frames"] > 0, f"{sid}: frames must be a positive integer")
        require(isinstance(item["sha256"], str) and re.fullmatch(r"[a-fA-F0-9]{64}", item["sha256"]), f"{sid}: invalid SHA256")
        name = item["path"]
        require(isinstance(name, str) and name and not any(c in name for c in "\\\n\r\t\x00:")
                and not PurePosixPath(name).is_absolute(), f"{sid}: path must be a relative filename")
        path = (manifest_path.parent / name).resolve()
        require(path.is_relative_to(project_root) and path.is_file(), f"{sid}: input must be an existing file inside the project root")
        require(path not in seen_paths, "The same input file cannot be selected twice")
        seen_paths.add(path)
        digest = file_sha(path)
        require(digest == item["sha256"].lower(), f"{sid}: SHA256 mismatch")
        facts = inspect(path, {**data, "frames": item["frames"]})
        require(file_sha(path) == digest, f"{sid}: input changed during validation")
        accepted.append({**item, "sha256": digest, "resolved_path": path, **facts})
    require(len({s["pixel_format"] for s in accepted}) == 1, "Input pixel formats must match")
    total_frames = sum(s["frames"] for s in accepted)
    plan = {"status": "validated_dry_run", "fps": FPS, "width": data["width"], "height": data["height"],
            "total_frames": total_frames, "duration_seconds": total_frames / FPS,
            "sample_rate": SAMPLE_RATE, "channels": 2, "total_audio_samples": total_frames * 2000,
            "manifest_sha256": file_sha(manifest_path), "output": output.relative_to(project_root).as_posix(),
            "segments": [{k: v for k, v in s.items() if k != "resolved_path"} for s in accepted]}
    return plan, accepted


def execute(plan, segments, output):
    # A fresh directory is the write boundary. No source file is changed or deleted.
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / "assembly-report.json"
    report = {**plan, "status": "running"}
    part = output / "master-native.part.mkv"
    final = output / "master-native.mkv"
    try:
        args = ["ffmpeg", "-nostdin", "-n", "-v", "error", "-xerror"]
        filters = []
        for i, item in enumerate(segments):
            require(file_sha(item["resolved_path"]) == item["sha256"], f"{item['id']}: source changed before assembly")
            args.extend(["-i", str(item["resolved_path"])])
            filters.extend([
                f"[{i}:v:0]setpts=N/(24*TB)[v{i}]",
                f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,apad,"
                f"atrim=end_sample={item['target_audio_samples']},asetpts=N/SR/TB[a{i}]",
            ])
        n = len(segments)
        filters.extend(["".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]",
                        "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"])
        args.extend(["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
                     "-c:v", "ffv1", "-level", "3", "-c:a", "pcm_s24le", "-fps_mode", "passthrough", str(part)])
        run(args)
        facts = inspect(part, {"width": plan["width"], "height": plan["height"], "frames": plan["total_frames"]}, exact_audio=True)
        run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(part), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
        require(facts["video_codec"] == "ffv1" and facts["audio_codec"] == "pcm_s24le", "Unexpected output codecs")
        for item in segments:
            require(file_sha(item["resolved_path"]) == item["sha256"], f"{item['id']}: source changed during assembly")
        report.update(status="verified", output_file=final.name, output_sha256=file_sha(part), verification=facts, full_decode=True)
        require(not final.exists(), "Final output appeared during assembly; refusing to replace it")
        part.rename(final)
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="edit/selected-segments.json, not episode.json")
    parser.add_argument("--output", required=True, type=Path, help="A new output directory; never overwritten")
    parser.add_argument("--project-root", type=Path, help="Defaults to the selected-segments directory's parent")
    parser.add_argument("--execute", action="store_true", help="Create the verified lossless master; default is read-only")
    args = parser.parse_args(argv)
    root = args.project_root or args.manifest.resolve().parent.parent
    try:
        plan, segments = validate(args.manifest, root, args.output)
        result = execute(plan, segments, args.output.resolve()) if args.execute else plan
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Invalid, OSError, subprocess.SubprocessError) as error:
        print(f"Assembly rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
