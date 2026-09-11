"""Offline JSON contract tests; no network, inference, or media inspection."""

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_graph.py"
SPEC = importlib.util.spec_from_file_location("prepare_graph", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    graph = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{model}}"}},
        "2": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": "{{seed}}", "cfg": "{{cfg}}",
            "steps": 20, "text": "Scene: {{prompt}}"}},
        "12": {"class_type": "SaveImage", "inputs": {
            "images": ["2", 0], "filename_prefix": "{{prefix}}"}},
    }
    values = {"model": "sdxl/example.safetensors", "seed": 0, "cfg": 7.5,
              "prompt": 'quoted "scene"\nnext line', "prefix": "run-001/shot-001"}
    return graph, values


class PrepareGraphTests(unittest.TestCase):
    def test_typed_binding_zero_seed_and_prompt_escaping(self):
        template, values = fixture()
        graph = MODULE.validate_graph(MODULE.bind(template, values), "12")
        self.assertIs(type(graph["2"]["inputs"]["seed"]), int)
        self.assertEqual(graph["2"]["inputs"]["seed"], 0)
        self.assertEqual(graph["2"]["inputs"]["cfg"], 7.5)
        self.assertEqual(graph["2"]["inputs"]["text"], 'Scene: quoted "scene"\nnext line')
        self.assertEqual(template["2"]["inputs"]["seed"], "{{seed}}")
        self.assertEqual(json.loads(MODULE.encoded(graph)), graph)

    def test_large_seed_keeps_integer_precision(self):
        template, values = fixture()
        values["seed"] = 2**64 - 1
        graph = MODULE.validate_graph(MODULE.bind(template, values), "12")
        self.assertEqual(json.loads(MODULE.encoded(graph))["2"]["inputs"]["seed"], 2**64 - 1)

    def test_missing_and_extra_parameters_fail(self):
        template, values = fixture()
        for changed in ({key: value for key, value in values.items() if key != "seed"},
                        {**values, "typo": 1}):
            with self.subTest(values=changed), self.assertRaisesRegex(ValueError, "parameter mismatch"):
                MODULE.bind(template, changed)

    def test_embedded_non_string_fails(self):
        template, values = fixture()
        values["prompt"] = 42
        with self.assertRaisesRegex(ValueError, "embedded parameter"):
            MODULE.bind(template, values)

    def test_placeholder_is_one_pass_and_malformed_tokens_fail(self):
        template, values = fixture()
        for text in ("{{seed}}", "{{ bad }}", "unfinished {{", "orphan }}"):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "placeholder"):
                MODULE.bind(template, {**values, "prompt": text})

    def test_invalid_seed_types_and_range_fail(self):
        template, values = fixture()
        for seed in (True, False, 0.0, "0", -1, 2**64, None):
            with self.subTest(seed=seed), self.assertRaisesRegex(ValueError, "seed must"):
                MODULE.validate_graph(MODULE.bind(template, {**values, "seed": seed}), "12")

    def test_invalid_dimensions_fail(self):
        template, values = fixture()
        graph = MODULE.bind(template, values)
        for width in (True, 0, -1, 512.0, "512"):
            graph["2"]["inputs"]["width"] = width
            with self.subTest(width=width), self.assertRaisesRegex(ValueError, "positive JSON integer"):
                MODULE.validate_graph(graph, "12")

    def test_model_names_and_prefix_paths_fail_closed(self):
        template, values = fixture()
        for field in ("model", "prefix"):
            for value in ("", "   ", None, "/absolute/file", "../file", "C:\\file",
                          "dir/../file", "dir//file", "https://host/file"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    MODULE.validate_graph(MODULE.bind(template, {**values, field: value}), "12")

    def test_bad_edges_fail(self):
        template, values = fixture()
        for edge in (["missing", 0], ["1", True], ["1", -1], ["1", 0.0], [1, 0], ["1"]):
            graph = MODULE.bind(template, values)
            graph["2"]["inputs"]["model"] = edge
            with self.subTest(edge=edge), self.assertRaisesRegex(ValueError, "invalid .*edge"):
                MODULE.validate_graph(graph, "12")

    def test_cycle_and_unrelated_branch_fail(self):
        template, values = fixture()
        graph = MODULE.bind(template, values)
        graph["1"]["inputs"]["cycle"] = ["2", 0]
        with self.assertRaisesRegex(ValueError, "cycle"):
            MODULE.validate_graph(graph, "12")
        graph = MODULE.bind(template, values)
        graph["99"] = {"class_type": "Unused", "inputs": {}}
        with self.assertRaisesRegex(ValueError, "do not contribute"):
            MODULE.validate_graph(graph, "12")

    def test_output_must_exist_be_supported_and_connected(self):
        template, values = fixture()
        graph = MODULE.bind(template, values)
        for target in ("missing", "2"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                MODULE.validate_graph(graph, target)
        graph["12"]["inputs"]["images"] = "not an edge"
        with self.assertRaisesRegex(ValueError, "connected images"):
            MODULE.validate_graph(graph, "12")

    def test_vhs_output_supported_only_when_saved(self):
        template, values = fixture()
        graph = MODULE.bind(template, values)
        graph["12"]["class_type"] = "VHS_VideoCombine"
        graph["12"]["inputs"]["save_output"] = True
        MODULE.validate_graph(graph, "12")
        graph["12"]["inputs"]["save_output"] = False
        with self.assertRaisesRegex(ValueError, "save_output"):
            MODULE.validate_graph(graph, "12")

    def test_savevideo_uses_video_edge(self):
        template, values = fixture()
        graph = MODULE.bind(template, values)
        graph["12"]["class_type"] = "SaveVideo"
        graph["12"]["inputs"]["video"] = graph["12"]["inputs"].pop("images")
        MODULE.validate_graph(graph, "12")

    def test_editor_graph_and_missing_inputs_fail(self):
        for graph in ({"nodes": [], "links": []}, {"1": {"class_type": "LoadImage"}}, {}):
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                MODULE.validate_graph(graph, "1")

    def test_json_duplicate_keys_and_nonfinite_values_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for text in ('{"seed": 1, "seed": 2}', '{"cfg": NaN}', '{"cfg": Infinity}'):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(ValueError):
                    MODULE.read_json(path)
        template, values = fixture()
        with self.assertRaisesRegex(ValueError, "non-finite"):
            MODULE.bind(template, {**values, "cfg": float("nan")})

    def test_cli_writes_matching_hash_and_pending_manifest_without_overwrite(self):
        template, values = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "template.json").write_bytes(MODULE.encoded(template))
            (root / "values.json").write_bytes(MODULE.encoded(values))
            args = ["--template", str(root / "template.json"), "--values", str(root / "values.json"),
                    "--output", str(root / "graph.json"), "--output-node", "12",
                    "--manifest", str(root / "prepared.json")]
            with contextlib.redirect_stdout(io.StringIO()):
                MODULE.main(args)
            graph_bytes = (root / "graph.json").read_bytes()
            manifest = MODULE.read_json(root / "prepared.json")
            self.assertEqual(manifest["graph_sha256"], hashlib.sha256(graph_bytes).hexdigest())
            self.assertEqual(manifest["state"], "prepared")
            self.assertEqual(manifest["visual_review"], "pending")
            self.assertFalse(manifest["inference_performed"])
            self.assertIsNone(manifest["prompt_id"])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                MODULE.main(args)
            self.assertEqual(error.exception.code, 2)
            self.assertEqual((root / "graph.json").read_bytes(), graph_bytes)

    def test_existing_manifest_does_not_leave_partial_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = Path(directory) / "graph.json"
            manifest = Path(directory) / "prepared.json"
            manifest.write_bytes(b"preserve")
            with self.assertRaises(FileExistsError):
                MODULE.write_exclusive([(graph, b"new"), (manifest, b"replace")])
            self.assertFalse(graph.exists())
            self.assertEqual(manifest.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
