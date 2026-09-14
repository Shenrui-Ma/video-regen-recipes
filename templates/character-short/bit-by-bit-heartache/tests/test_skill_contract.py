import json
from pathlib import Path
import re
import unittest

T=Path(__file__).resolve().parents[1]

class SkillContractTests(unittest.TestCase):
    def test_entry_is_standalone_and_links_resolve(self):
        for name in ('SKILL.md','README.md'):
            text=(T/name).read_text()
            self.assertNotIn('../../../skills/',text)
            for target in re.findall(r'\]\(([^)]+)\)',text):
                if '://' in target or target.startswith('#'): continue
                path=(T/target.split('#')[0]).resolve()
                self.assertTrue(path.is_relative_to(T),target)
                self.assertTrue(path.exists(),target)
        text=(T/'SKILL.md').read_text()
        self.assertTrue(text.startswith('---\n'))
        front=text.split('---',2)[1]
        for field in ('name:','description:','version:','author:','license:','platforms:'):
            self.assertIn(field,front)
        self.assertIn('干净', (T/'references/validation.md').read_text())

    def test_current_profile_exposes_packaged_runtime(self):
        p=json.loads((T/'profile.json').read_text())
        self.assertNotIn('not-packaged',p['status'])
        self.assertEqual(p['runtime']['entry'],'scripts/runtime/heartache.py')
        for key in ('entry','asset_manifest','environment_lock'):
            self.assertTrue((T/p['runtime'][key]).is_file(), key)
        lock = json.loads((T/p['runtime']['environment_lock']).read_text())
        self.assertEqual(lock['environment'], 'environments/h3')
        self.assertRegex(lock['commit'], r'^[0-9a-f]{40}$')
        self.assertFalse(p['runtime']['clean_install_inference_verified'])

if __name__=='__main__': unittest.main()
