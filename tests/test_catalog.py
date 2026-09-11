import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('catalog',ROOT/'scripts/catalog.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class CatalogTests(unittest.TestCase):
    def test_alias_case_and_punctuation(self):
        data=m.collect(ROOT/'templates')
        self.assertEqual(m.search(data,'一滴一滴刺痛我的心')[0]['id'],'bit-by-bit-heartache')
        self.assertIn('mygo-ave-mujica-episode', {r['id'] for r in m.search(data,'Ａｖｅ　Ｍｕｊｉｃａ')})
        self.assertIn('mygo-ave-mujica-episode', {r['id'] for r in m.search(data,'MyGO!!!!!')})

    def test_tag_intersection_and_no_match(self):
        data=m.collect(ROOT/'templates')
        self.assertEqual(len(m.search(data,tags=['舞蹈','音乐短片'])),2)
        self.assertEqual(m.search(data,'not-an-existing-recipe'),[])
        self.assertEqual(m.search(data,tags=['舞蹈','多人对白']),[])

    def make_tree(self,root):
        profile=json.loads((ROOT/'templates/character-short/not-a-sin/profile.json').read_text())
        profile['files']={'guide':'README.md','agent_entry':'SKILL.md'}
        folder=root/'category/recipe';folder.mkdir(parents=True)
        (folder/'README.md').write_text('# Recipe')
        (folder/'SKILL.md').write_text('# Entry')
        (folder/'profile.json').write_text(json.dumps(profile))
        return folder,profile

    def test_variants_and_empty_categories_do_not_increase_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,profile=self.make_tree(root)
            profile['index']['variants']=['a','b']
            (folder/'profile.json').write_text(json.dumps(profile))
            (root/'empty').mkdir()
            (root/'asset').mkdir();(root/'asset/profile.json').write_text('{}')
            data=m.collect(root)
            self.assertEqual(data['template_count'],1)
            self.assertEqual(data['templates'][0]['variants'],['a','b'])

    def test_duplicate_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,profile=self.make_tree(root)
            other=root/'category/another';other.mkdir()
            for name in ['README.md','SKILL.md','profile.json']:(other/name).write_bytes((folder/name).read_bytes())
            with self.assertRaisesRegex(ValueError,'unique'):m.collect(root)

    def test_broken_entry_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder,profile=self.make_tree(root)
            (folder/'SKILL.md').unlink()
            with self.assertRaisesRegex(ValueError,'SKILL.md'):m.collect(root)
            (folder/'SKILL.md').write_text('# Entry')
            (root/'outside.md').write_text('# Outside')
            profile['files']['guide']='../../outside.md'
            (folder/'profile.json').write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError,'outside'):m.collect(root)

    def test_checked_in_outputs_match_profiles(self):
        data=m.collect(ROOT/'templates')
        self.assertEqual(json.loads((ROOT/'templates/catalog.json').read_text()),data)
        self.assertEqual((ROOT/'templates/README.md').read_text(),m.markdown(data))
        homepage=(ROOT/'README.md').read_text()
        self.assertEqual(homepage,m.homepage_count(homepage,data['template_count']))

    def test_homepage_count_preserves_surrounding_content(self):
        before='# Project\n\nIntro\n\n### 🎬 已收录 [8 个视频模板](templates/) · 持续更新\n\n![Hero](assets/hero.png)\n\n## TODO\n- [ ] Windows\n'
        after=m.homepage_count(before,9)
        self.assertEqual(after,before.replace('[8 个视频模板]','[9 个视频模板]'))
        self.assertEqual(m.homepage_count(after,9),after)

    def test_missing_or_duplicate_homepage_counter_fails(self):
        line='### 🎬 已收录 [8 个视频模板](templates/) · 持续更新\n'
        for text in ['# Project\n',line+line]:
            with self.assertRaisesRegex(ValueError,'exactly one'):m.homepage_count(text,9)

    def test_build_counts_added_and_removed_recipes_without_manual_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder,profile=self.make_tree(root/'templates')
            (root/'README.md').write_text('# Project\n\n### 🎬 已收录 [99 个视频模板](templates/) · 持续更新\n\nKeep this text.\n')
            with patch.object(m,'ROOT',root):
                self.assertEqual(m.main(['build']),0)
                self.assertEqual(m.main(['check']),0)
                self.assertIn('[1 个视频模板]',(root/'README.md').read_text())
                other=folder.parent/'new'
                other.mkdir()
                for name in ('README.md','SKILL.md'):
                    (other/name).write_text((folder/name).read_text())
                profile['id']='second-recipe'
                (other/'profile.json').write_text(json.dumps(profile))
                self.assertEqual(m.main(['build']),0)
                self.assertIn('[2 个视频模板]',(root/'README.md').read_text())
                (other/'profile.json').unlink()
                self.assertEqual(m.main(['build']),0)
                self.assertEqual(m.main(['check']),0)
                self.assertIn('[1 个视频模板]',(root/'README.md').read_text())
                self.assertTrue((root/'README.md').read_text().endswith('Keep this text.\n'))

    def test_cover_and_visualizer_are_independent_entries(self):
        data=m.collect(ROOT/'templates')
        cover=next(r for r in data['templates'] if r['id']=='girls-band-ddsp-cover')
        visualizer=next(r for r in data['templates'] if r['id']=='rhythm-ring-mv')
        self.assertNotEqual(cover['agent_entry'],visualizer['agent_entry'])
        self.assertNotEqual(cover['category'],visualizer['category'])
        self.assertEqual(m.search(data,'律动环')[0]['id'],'rhythm-ring-mv')

if __name__=='__main__':unittest.main()
