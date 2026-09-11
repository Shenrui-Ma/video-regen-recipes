import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import wave
import zlib
import struct


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_episode.py"
SPEC = importlib.util.spec_from_file_location("build_episode", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.episode = {
            "schema_version": 1, "title": "A short conversation", "franchise": "MyGO!!!!!",
            "fps": 24, "width": 768, "height": 448, "steps": 20,
            "model_files": {key: key + ".safetensors" for key in ("diffusion_model", "text_encoder", "video_vae", "audio_vae")},
            "characters": {}, "scenes": {"room": {"description": "An empty rehearsal room.", "image": "assets/room.png"}},
            "shots": [{"id": "s01", "scene": "room", "cast": ["tomori", "anon"], "frames": 243, "seed": 42,
                       "visual_description": "@anon stands beside @tomori in a steady medium shot.",
                       "dialogue": [{"character": "anon", "text": "一緒に帰ろう。", "delivery": "Warm and quiet"},
                                    {"character": "tomori", "text": "うん。", "delivery": "Soft, with relief"},
                                    {"character": "anon", "text": "よかった。", "delivery": "Smiling"}],
                       "ambience": "Quiet room tone."}],
        }
        for cid in ("tomori", "anon"):
            self.episode["characters"][cid] = {
                "name": cid.title(), "appearance": f"The appearance shown in {cid}'s identity image.",
                "identity_image": f"assets/{cid}.png", "turnaround_image": f"assets/{cid}-turnaround.png",
                "voice_audio": f"assets/{cid}.wav",
            }
        self.names = ["assets/room.png"]
        for char in self.episode["characters"].values():
            self.names.extend(char[key] for key in ("identity_image", "turnaround_image", "voice_audio"))
        for name in self.names:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(("fixture:" + name).encode())
        self.bindings = {"schema_version": 1, "files": {}}
        for name in self.names:
            digest = builder.file_sha(self.root / name)
            self.bindings["files"][digest] = {"name": "episode-inputs/" + Path(name).name, "sha256": digest}
        self.episode_path, self.bindings_path = self.root / "episode.json", self.root / "bindings.json"
        self.write_inputs()
        self.probe = patch.object(builder, "probe_media", side_effect=self.fake_probe).start()
        self.addCleanup(patch.stopall)

    def write_inputs(self):
        self.episode_path.write_text(json.dumps(self.episode), encoding="utf-8")
        self.bindings_path.write_text(json.dumps(self.bindings), encoding="utf-8")

    @staticmethod
    def fake_probe(path):
        if path.suffix == ".wav":
            return {"streams": [{"codec_type": "audio", "codec_name": "pcm_s24le", "duration": "3.0", "sample_rate": "48000", "channels": 2}]}
        return {"streams": [{"codec_type": "video", "codec_name": "png", "width": 64, "height": 64}]}

    def validate(self, **kwargs):
        return builder.validate_episode(self.episode, self.root, **kwargs)

    def test_dialogue_order_drives_audio_and_turnarounds_independently_of_cast(self):
        item = self.validate()[0]
        self.assertEqual(item["speakers"], ["anon", "tomori"])
        self.assertEqual([a.get("character") for a in item["images"]], ["tomori", "anon", "anon", "tomori", None])
        graph, prompt = builder.make_graph(self.episode, item, self.bindings["files"], "output/s01")
        self.assertIn("<Audio 1> provides the voice timbre of <Subject 2> (S1)", prompt)
        self.assertIn("<Subject 2> (S1) speaks using the voice of <Audio 1>", prompt)
        self.assertIn("<Subject 1> (S2) speaks using the voice of <Audio 2>", prompt)
        self.assertIn("<d>[Japanese] 一緒に帰ろう。</d>", prompt)
        self.assertEqual(prompt.count("<d>[Japanese]"), 3)
        self.assertEqual(prompt.count("<Subject 2> (S1) speaks"), 2)
        self.assertNotIn("(S", prompt.split("retention_analysis:\n")[1].split("detailed_description:\n")[0])
        self.assertIn("<Subject 2> stands beside <Subject 1>", prompt)
        self.assertEqual(graph["136"]["inputs"]["ref_audios.ref_audio_0"], ["220", 0])
        self.assertEqual(graph["220"]["inputs"]["audio"], "episode-inputs/anon.wav")
        self.assertEqual(graph["202"]["inputs"]["image"], "episode-inputs/anon-turnaround.png")

    def test_graph_is_independent_joint_av_and_has_no_template_tokens(self):
        graph, prompt = builder.make_graph(self.episode, self.validate()[0], self.bindings["files"], "output/s01")
        self.assertEqual(graph["125"]["inputs"]["latent_image"], ["136", 1])
        self.assertEqual(graph["121"]["inputs"]["samples"], ["125", 0])
        self.assertEqual(graph["122"]["inputs"]["samples"], ["125", 0])
        self.assertNotIn("first_frame", graph["136"]["inputs"])
        self.assertNotIn("{{", json.dumps(graph))
        self.assertIs(type(graph["136"]["inputs"]["length"]), int)
        self.assertEqual(sum(prompt.count(header + ":\n") for header in ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")), 6)

    def test_reference_prompt_markers_and_combined_subject_definitions(self):
        prompt = builder.build_prompt(self.episode, self.validate()[0])
        definitions = prompt.split("subject_definitions:\n", 1)[1].split("summary:\n", 1)[0]
        subject_one = next(line for line in definitions.splitlines() if line.startswith("<Subject 1>"))
        subject_two = next(line for line in definitions.splitlines() if line.startswith("<Subject 2>"))
        self.assertIn("<Picture 1>", subject_one)
        self.assertIn("<Picture 4>", subject_one)
        self.assertIn("<Picture 2>", subject_two)
        self.assertIn("<Picture 3>", subject_two)
        self.assertFalse(any(line.startswith("<Picture ") for line in definitions.splitlines()))
        self.assertIn("summary:\n[reference generation + audio reference]", prompt)
        retention = prompt.split("retention_analysis:\n", 1)[1].split("detailed_description:\n", 1)[0]
        self.assertIn("<Subject 1>: fully_preserved -", retention)
        self.assertIn("<Subject 2>: fully_preserved -", retention)
        self.assertIn("<Subject 3>: weak_reference -", retention)
        self.assertIn("<Audio 1>: reference -", retention)
        self.assertIn("<Audio 2>: reference -", retention)
        self.assertNotIn("(S", retention)
        self.assertEqual(prompt.split("non_diegetic_music:\n", 1)[1].strip(), "N/A")

    def test_export_six_segment_contract_and_no_overwrite(self):
        self.episode["shots"] = [{**copy.deepcopy(self.episode["shots"][0]), "id": f"s{index:02}", "frames": 226 if index == 6 else 243, "seed": index} for index in range(1, 7)]
        self.write_inputs()
        output = self.root / "build-v1"
        manifest = builder.export_episode(self.episode_path, self.bindings_path, output)
        self.assertEqual(manifest["total_expected_frames"], 1441)
        self.assertEqual(len(list((output / "api").glob("*.json"))), 6)
        self.assertEqual(manifest["status"], "built-not-submitted")
        graph_file = output / manifest["shots"][0]["api_graph"]
        self.assertEqual(builder.file_sha(graph_file), manifest["shots"][0]["api_sha256"])
        self.assertFalse((output / ".incomplete").exists())
        with self.assertRaisesRegex(builder.Invalid, "already exists"):
            builder.export_episode(self.episode_path, self.bindings_path, output)

    def test_undeclared_role_and_manual_reference_number_fail(self):
        for description in ("@soyo enters.", "<Subject 1> enters.", "@ enters."):
            with self.subTest(description=description):
                self.episode["shots"][0]["visual_description"] = description
                with self.assertRaises(builder.Invalid):
                    self.validate()

    def test_bad_frames_canvas_and_seed_fail(self):
        original = copy.deepcopy(self.episode)
        for section, key, value in [("episode", "width", 1080), ("episode", "height", 600), ("episode", "fps", 30),
                                    ("episode", "steps", 8), ("shot", "frames", 240), ("shot", "seed", -1), ("shot", "seed", True)]:
            with self.subTest(key=key, value=value):
                self.episode = copy.deepcopy(original)
                target = self.episode if section == "episode" else self.episode["shots"][0]
                target[key] = value
                with self.assertRaises(builder.Invalid):
                    self.validate()

    def test_turnaround_omission_is_explicit_and_recorded(self):
        self.episode["characters"]["anon"]["turnaround_image"] = None
        with self.assertRaisesRegex(builder.Invalid, "allow-missing-turnarounds"):
            self.validate()
        item = self.validate(allow_missing_turnarounds=True)[0]
        self.assertEqual(item["omitted_turnarounds"], ["anon"])
        self.assertEqual(len(item["images"]), 4)

    def test_flag_does_not_hide_a_missing_named_turnaround(self):
        (self.root / "assets/anon-turnaround.png").unlink()
        with self.assertRaisesRegex(builder.Invalid, "Missing or empty"):
            self.validate(allow_missing_turnarounds=True)

    def test_audio_duration_individual_and_total_limits(self):
        for duration in ("1.9", "8.0", "15.1", "nan"):
            with self.subTest(duration=duration):
                def probe(path):
                    data = self.fake_probe(path)
                    if path.suffix == ".wav":
                        data["streams"][0]["duration"] = duration
                    return data
                self.probe.side_effect = probe
                with self.assertRaises(builder.Invalid):
                    self.validate()

    def test_missing_binding_does_not_create_output(self):
        self.bindings["files"].pop(builder.file_sha(self.root / "assets/anon.wav"))
        self.write_inputs()
        output = self.root / "build-v1"
        with self.assertRaisesRegex(builder.Invalid, "No verified"):
            builder.export_episode(self.episode_path, self.bindings_path, output)
        self.assertFalse(output.exists())

    def test_binding_digest_disagreement_and_name_collision_fail(self):
        entries = list(self.bindings["files"].values())
        entries[0]["sha256"] = "a" * 64
        with self.assertRaisesRegex(builder.Invalid, "disagree"):
            builder.validate_bindings(self.bindings)
        entries[0]["sha256"] = next(iter(self.bindings["files"]))
        entries[1]["name"] = entries[0]["name"]
        with self.assertRaisesRegex(builder.Invalid, "share"):
            builder.validate_bindings(self.bindings)

    def test_binding_escapes_urls_and_annotations_fail(self):
        entry = next(iter(self.bindings["files"].values()))
        for name in ("/tmp/file.wav", "../file.wav", "C:\\input\\file.wav", "https://example.org/file.wav", "x.wav [output]"):
            with self.subTest(name=name):
                entry["name"] = name
                with self.assertRaises(builder.Invalid):
                    builder.validate_bindings(self.bindings)

    def test_changed_asset_invalidates_binding(self):
        (self.root / "assets/anon.wav").write_bytes(b"changed")
        with self.assertRaisesRegex(builder.Invalid, "No verified"):
            builder.export_episode(self.episode_path, self.bindings_path, self.root / "build-v1")

    def test_local_asset_symlink_escape_fails(self):
        image = self.root / "assets/anon.png"
        image.unlink()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "image.png"
            target.write_bytes(b"outside")
            image.symlink_to(target)
            with self.assertRaisesRegex(builder.Invalid, "escapes"):
                self.validate()

    def test_unfilled_placeholder_and_duplicate_json_key_fail(self):
        for value in ("{{diffusion_model}}", "REPLACE_WITH_INSTALLED_DIFFUSION_MODEL_NAME"):
            self.episode["model_files"]["diffusion_model"] = value
            with self.assertRaisesRegex(builder.Invalid, "placeholder"):
                self.validate()
        broken = self.root / "duplicate.json"
        broken.write_text('{"schema_version": 1, "schema_version": 2}')
        with self.assertRaisesRegex(builder.Invalid, "Duplicate JSON"):
            builder.read_json(broken)

    def test_empty_speaker_and_unknown_schema_fields_fail(self):
        self.episode["shots"][0]["dialogue"] = []
        with self.assertRaises(builder.Invalid):
            self.validate()
        self.episode["unexpected"] = True
        with self.assertRaisesRegex(builder.Invalid, "unknown fields"):
            self.validate()

    def test_selected_shot_does_not_require_unused_character_or_scene_assets(self):
        self.episode["shots"][0]["id"] = "01"
        self.episode["characters"]["soyo"] = {"appearance": "REPLACE_WITH_VISIBLE_FEATURES"}
        self.episode["scenes"]["hall"] = {"image": "REPLACE_WITH_SCENE_PATH"}
        self.episode["shots"].append({"id": "02", "scene": "hall", "cast": ["soyo"]})
        self.write_inputs()
        manifest = builder.export_episode(self.episode_path, self.bindings_path, self.root / "build-v1", selected_shots=["01"])
        self.assertEqual(manifest["selected_shots"], ["01"])
        self.assertEqual(manifest["total_expected_frames"], 243)
        self.assertTrue((self.root / "build-v1/api/01.json").is_file())
        with self.assertRaises(builder.Invalid):
            self.validate()

    def test_unknown_or_duplicate_selection_fails(self):
        for selection in (["missing"], ["s01", "s01"]):
            with self.subTest(selection=selection), self.assertRaises(builder.Invalid):
                self.validate(selected_shots=selection)

    def test_language_is_explicit_and_preformatted_dialogue_is_rejected(self):
        self.episode["dialogue_language"] = "Chinese"
        graph, prompt = builder.make_graph(self.episode, self.validate()[0], self.bindings["files"], "output/s01")
        self.assertIn("<d>[Chinese]", prompt)
        self.episode["dialogue_language"] = "Japanese]<d>"
        with self.assertRaisesRegex(builder.Invalid, "dialogue_language"):
            self.validate()
        self.episode["dialogue_language"] = "Japanese"
        for words in ("<d>台詞</d>", "[Shot 2] 台詞", "<Audio 1> 台詞", "[Japanese] 台詞", "(S1) 台詞"):
            self.episode["shots"][0]["dialogue"][0]["text"] = words
            with self.subTest(words=words), self.assertRaisesRegex(builder.Invalid, "plain spoken"):
                self.validate()


class RealAudioProbeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe is unavailable")
    def test_real_pcm_wav_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root / "reference.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(b"\0\0" * 96000)
            record = builder.inspect_asset(root, "reference.wav", "audio", {})
            self.assertEqual(record["duration_seconds"], 2.0)
            self.assertEqual(record["sample_rate"], 48000)
            self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe is unavailable")
    def test_shipped_examples_build_with_real_synthetic_assets(self):
        examples = sorted((SCRIPT.parents[1] / "examples").glob("episode.*.json"))
        self.assertEqual(len(examples), 2)
        def png_bytes(red):
            def chunk(kind, data):
                return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
            return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress((b"\0" + bytes((red, 0, 128)) * 2) * 2)) + chunk(b"IEND", b""))
        for example in examples:
            with self.subTest(example=example.name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                episode = builder.read_json(example)
                for key in episode["model_files"]:
                    episode["model_files"][key] = key + ".safetensors"
                paths = set()
                for char in episode["characters"].values():
                    char["appearance"] = "Distinct hair, eyes and fixed clothing from the supplied identity reference."
                    paths.update(char[key] for key in ("identity_image", "turnaround_image", "voice_audio"))
                paths.update(scene["image"] for scene in episode["scenes"].values())
                bindings = {"schema_version": 1, "files": {}}
                for index, name in enumerate(sorted(paths), 1):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == ".wav":
                        with wave.open(str(path), "wb") as wav:
                            wav.setnchannels(1)
                            wav.setsampwidth(2)
                            wav.setframerate(48000)
                            wav.writeframes(struct.pack("<h", index) * 96000)
                    else:
                        path.write_bytes(png_bytes(index))
                    digest = builder.file_sha(path)
                    bindings["files"][digest] = {"name": "test-inputs/" + name, "sha256": digest}
                episode_path, bindings_path = root / "episode.json", root / "bindings.json"
                episode_path.write_text(json.dumps(episode), encoding="utf-8")
                bindings_path.write_text(json.dumps(bindings), encoding="utf-8")
                manifest = builder.export_episode(episode_path, bindings_path, root / "build-v1")
                self.assertEqual(manifest["total_expected_frames"], 1441)
                self.assertEqual([shot["id"] for shot in manifest["shots"]], ["01", "02", "03", "04", "05", "06"])
                for shot in manifest["shots"]:
                    graph = builder.read_json(root / "build-v1" / shot["api_graph"])
                    prompt = graph["136"]["inputs"]["prompt"]
                    self.assertNotIn("{{", json.dumps(graph))
                    self.assertNotIn("REPLACE_", json.dumps(graph))
                    self.assertIn("<d>[Japanese]", prompt)
                    self.assertIn("[Shot 1]", prompt)
                    self.assertIn("summary:\n[reference generation + audio reference]", prompt)
                    retention = prompt.split("retention_analysis:\n", 1)[1].split("detailed_description:\n", 1)[0]
                    self.assertNotIn("(S", retention)
                    self.assertEqual(prompt.split("non_diegetic_music:\n", 1)[1].strip(), "N/A")
                    for subject_number, cid in enumerate(shot["cast_order"], 1):
                        self.assertIn(f"<Subject {subject_number}>: fully_preserved -", retention)
                    self.assertIn(f"<Subject {len(shot['cast_order']) + 1}>: weak_reference -", retention)
                    for speaker_number, cid in enumerate(shot["speaker_order"], 1):
                        subject_number = shot["cast_order"].index(cid) + 1
                        self.assertIn(f"<Audio {speaker_number}> provides the voice timbre of <Subject {subject_number}> (S{speaker_number})", prompt)
                        self.assertIn(f"<Subject {subject_number}> (S{speaker_number}) speaks", prompt)
                        self.assertIn(f"<Audio {speaker_number}>: reference -", retention)


if __name__ == "__main__":
    unittest.main()
