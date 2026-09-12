#!/usr/bin/env python3
"""Build a v2/48k/F0/speaker-0 filelist from a four-modality intersection."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

from run_guard import require_regular, resource_path, sha256, write_new_json


MODALITIES = {
    "wav": ("0_gt_wavs", ".wav"),
    "feature768": ("3_feature768", ".npy"),
    "f0": ("2a_f0", ".wav.npy"),
    "f0nsf": ("2b-f0nsf", ".wav.npy"),
}


def safe_text(value):
    if any(char in str(value) for char in ("|", "\n", "\r")):
        raise ValueError("Filelist paths cannot contain pipes or newlines")


def collect(experiment):
    modalities = {}
    for key, (directory, suffix) in MODALITIES.items():
        folder = experiment / directory
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Missing or linked modality directory: " + directory)
        files = {}
        for path in sorted(folder.iterdir()):
            if not path.name.endswith(suffix):
                continue
            safe_text(path)
            require_regular(path)
            name = path.name[:-len(suffix)]
            if not name:
                raise ValueError("Empty sample ID")
            files[name] = path
        modalities[key] = files
    return modalities


def build(experiment, mute_root, allow_incomplete=False):
    modalities = collect(experiment)
    sets = [set(files) for files in modalities.values()]
    union = set.union(*sets)
    intersection = set.intersection(*sets)
    if not intersection:
        raise ValueError("No complete character samples")
    excluded = {name: [key for key, files in modalities.items() if name not in files]
                for name in sorted(union - intersection)}
    if excluded and not allow_incomplete:
        raise ValueError("Incomplete modalities; review missing IDs before --allow-incomplete: "
                         + json.dumps(excluded, sort_keys=True))
    mute = [mute_root / "0_gt_wavs/mute48k.wav",
            mute_root / "3_feature768/mute.npy",
            mute_root / "2a_f0/mute.wav.npy",
            mute_root / "2b-f0nsf/mute.wav.npy"]
    sample_paths = [[modalities[key][name] for key in MODALITIES] for name in sorted(intersection)]
    # A mute fixture is never counted as a character sample, including hard links.
    for path in mute:
        safe_text(path)
        resource_path(mute_root, str(path))
        require_regular(path)
        if any(path.samefile(candidate) for row in sample_paths for candidate in row):
            raise ValueError("Mute and character files overlap")
    rows = ["|".join(map(str, paths)) + "|0" for paths in sample_paths]
    random.Random(20260731).shuffle(rows)
    mute_row = "|".join(map(str, mute)) + "|0"
    text = "\n".join(rows + [mute_row, mute_row]) + "\n"
    hashes = {name: {key: sha256(modalities[key][name]) for key in MODALITIES}
              for name in sorted(intersection)}
    report = {
        "schema_version": 1, "profile": "v2-48k-f0-speaker0",
        "modality_counts": {key: len(files) for key, files in modalities.items()},
        "character_rows": len(rows), "mute_rows": 2, "total_rows": len(rows) + 2,
        "excluded_missing_modalities": excluded, "sample_sha256": hashes,
        "mute_sha256": {key: sha256(path) for key, path in zip(MODALITIES, mute)},
        "filelist_seed": 20260731, "training_seed": "not-controlled-by-this-helper",
        "filelist_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "not_checked": ["audio decoding", "NPY shape, finiteness and frame alignment",
                        "speaker identity", "holdout isolation", "authorization", "index internals"],
    }
    return text, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--mute-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="Explicitly accept the reported incomplete-sample exclusions")
    args = parser.parse_args(argv)
    try:
        experiment = resource_path(Path.cwd(), str(args.experiment))
        mute_root = resource_path(Path.cwd(), str(args.mute_root))
        outputs = [args.output.resolve(), args.report.resolve()]
        if outputs[0] == outputs[1] or any(path.exists() for path in outputs):
            raise ValueError("Output and report must be distinct new files")
        for path in outputs:
            if path.is_relative_to(mute_root) or any(
                path.is_relative_to(experiment / directory) for directory, _ in MODALITIES.values()
            ):
                raise ValueError("Do not write outputs into modality or mute directories")
        text, report = build(experiment, mute_root, args.allow_incomplete)
        # Exclusive creation prevents clobbering. A partial pair is not a valid receipt.
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        write_new_json(args.report, report)
        print(json.dumps({"status": "built", "character_rows": report["character_rows"],
                          "mute_rows": 2, "excluded": len(report["excluded_missing_modalities"])}))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
