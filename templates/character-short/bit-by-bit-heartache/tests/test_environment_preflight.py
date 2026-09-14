import importlib.util
import pathlib
import tempfile
import unittest

T = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = T / 'scripts/environment/preflight.py'


def load():
    spec = importlib.util.spec_from_file_location('heartache_preflight', SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PreflightTests(unittest.TestCase):
    def test_cli_offline_reports_unsupported_platform_without_ready_claim(self):
        import json, subprocess, sys
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--platform', 'Darwin',
                                 '--architecture', 'arm64'], capture_output=True, text=True)
        self.assertTrue(result.stdout.strip(), 'No usable preflight CLI implemented')
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(report['ready_for_inference'])
        self.assertIn('unsupported_platform', [i['code'] for i in report['issues']])
        self.assertEqual(report['network_methods'], [])

    def test_dynamic_combo_accepts_keys_and_requires_selected_branch_fields(self):
        mod = load()
        info = {'Save': {'input': {'required': {'codec': ['COMFY_DYNAMICCOMBO_V3', {
            'options': [{'key': 'auto', 'inputs': {'required': {}}},
                        {'key': 'h264', 'inputs': {'required': {'crf': ['FLOAT', {'min': 0, 'max': 51}]}}}]}]}}}}
        graph = {'1': {'class_type': 'Save', 'inputs': {'codec': 'h264', 'codec.crf': 18.0}}}
        self.assertEqual(mod.check_graph(graph, info), [])
        del graph['1']['inputs']['codec.crf']
        self.assertIn('required_input_missing', {i['code'] for i in mod.check_graph(graph, info)})

    def test_v3_nested_autogrow_and_wrong_link_type(self):
        mod = load()
        spec = {'refs': ['COMFY_AUTOGROW_V3', {'template': {
            'prefix': 'ref_', 'max': 2, 'input': {'required': {'image': ['IMAGE']}}}}]}
        self.assertEqual(mod.input_spec(spec, 'refs.ref_0'), ['IMAGE'])
        self.assertIsNone(mod.input_spec(spec, 'refs.ref_2'))
        info = {'A': {'output': ['AUDIO']},
                'B': {'input': {'required': {'image': ['IMAGE']}}}}
        codes = {x['code'] for x in mod.check_graph({
            '1': {'class_type': 'A', 'inputs': {}},
            '2': {'class_type': 'B', 'inputs': {'image': ['1', 0]}}}, info)}
        self.assertIn('link_type_mismatch', codes)

    def test_nodes_installed_but_disabled_are_not_missing_packages(self):
        mod = load()
        self.assertTrue(hasattr(mod, 'check_nodes'), 'node diagnostics missing')
        result = mod.check_nodes({'MiniMaxH3MotionContext': {'package': 'motion-context'}}, {},
                                 {'motion-context': {'installed': True}},
                                 ['main.py', '--disable-all-custom-nodes'])
        self.assertEqual(result[0]['code'], 'node_disabled')

    def test_schema_rejects_wrong_output_slots_and_unknown_fields(self):
        mod = load()
        self.assertTrue(hasattr(mod, 'check_graph'), 'schema checker missing')
        info = {'Source': {'input': {'required': {}}, 'output': ['IMAGE']},
                'Sink': {'input': {'required': {'image': ['IMAGE']}}, 'output': []}}
        graph = {'1': {'class_type': 'Source', 'inputs': {}},
                 '2': {'class_type': 'Sink', 'inputs': {'image': ['1', 1], 'wrong': 4}}}
        codes = {x['code'] for x in mod.check_graph(graph, info)}
        self.assertIn('link_output_slot_mismatch', codes)
        self.assertIn('unknown_input', codes)

    def test_missing_model_is_not_ready(self):
        self.assertTrue(SCRIPT.exists(), 'read-only preflight has not been implemented')
        spec = importlib.util.spec_from_file_location('heartache_preflight', SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as root:
            report = mod.check_models([{'target': 'models/vae/test.safetensors', 'bytes': 3, 'sha256': '0'*64}], pathlib.Path(root))
        self.assertEqual(report[0]['code'], 'missing_model')


if __name__ == '__main__':
    unittest.main()
