import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('render_default',Path(__file__).parents[1]/'scripts/render_default.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class TimelineTests(unittest.TestCase):
    def test_pr_visible_ranges_sum_to1587(self):
        self.assertEqual(sum(m.KEEP),1587)
        self.assertEqual(sum(m.KEEP)/m.FPS,26.45)
        self.assertEqual(m.SOURCE_FRAMES,[158,158,175,175])
    def test_final_music_and_timeline_filter(self):
        graph=m.filter_graph()
        for i,n in enumerate([395,373,382,437]):self.assertIn(f'[{i}:v]fps=60,trim=start_frame=0:end_frame={n}',graph)
        self.assertIn('afade=t=out:st=25.95:d=0.5',graph)
        self.assertNotIn('atempo',graph)
        self.assertNotIn('rife',graph.lower())

if __name__=='__main__':unittest.main()
