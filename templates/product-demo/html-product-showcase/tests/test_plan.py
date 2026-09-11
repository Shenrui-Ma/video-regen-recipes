import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('product_plan', ROOT/'scripts/plan.py')
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'examples/storyboard.json').read_text())

    def test_example_has_two_six_second_scenes(self):
        plan = planner.compile_plan(self.data)
        self.assertEqual(plan['total_frames'], 360)
        self.assertEqual(plan['duration_seconds'], 12)
        self.assertEqual([s['start_frame'] for s in plan['scenes']], [0,180])

    def test_overlap_changes_global_but_not_local_beats(self):
        self.data['scenes'][0]['overlap_out_frames'] = 12
        result = planner.compile_plan(self.data)
        self.assertEqual(result['total_frames'],348)
        self.assertEqual(result['scenes'][1]['start_frame'],168)
        self.assertEqual(result['scenes'][1]['beats'],self.data['scenes'][1]['beats'])

    def test_last_transition_and_consumed_scene_fail(self):
        for value in [12,180]:
            data = copy.deepcopy(self.data)
            if value == 12:
                data['scenes'][-1]['overlap_out_frames'] = value
            else:
                data['scenes'][0]['overlap_out_frames'] = value
            with self.assertRaises(ValueError): planner.compile_plan(data)

    def test_beats_must_be_ordered_and_within_scene(self):
        for start,end in [(20,50),(45,181),(60,50)]:
            data = copy.deepcopy(self.data)
            data['scenes'][0]['beats'][1].update(start_frame=start,end_frame=end)
            with self.assertRaises(ValueError): planner.compile_plan(data)

    def test_geometry_and_numeric_types(self):
        for key,value in [('width',1919),('fps',True),('fps',30.5),('height',8192)]:
            data=copy.deepcopy(self.data);data['output'][key]=value
            with self.assertRaises(ValueError):planner.compile_plan(data)

    def test_duplicate_ids_and_missing_evidence_fail(self):
        data=copy.deepcopy(self.data);data['scenes'][1]['id']=data['scenes'][0]['id']
        with self.assertRaises(ValueError):planner.compile_plan(data)
        self.data['scenes'][0]['evidence']=''
        with self.assertRaises(ValueError):planner.compile_plan(self.data)


if __name__=='__main__':unittest.main()
