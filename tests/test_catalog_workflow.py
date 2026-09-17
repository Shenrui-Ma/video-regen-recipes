import json
import re
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('git') and shutil.which('bash'), 'Git and Bash required')
class CatalogWorkflowTests(unittest.TestCase):
    def git(self, directory, *args):
        return subprocess.run([shutil.which('git'), '-C', str(directory), *args],
                              check=True, text=True, capture_output=True)

    def commit(self, directory):
        self.git(directory, 'add', '.')
        self.git(directory, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-m', 'Update local test fixture')

    def test_ci_guard_does_not_touch_local_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env.pop('GITHUB_ACTIONS', None)
            result = subprocess.run(['bash', str(ROOT / 'scripts/ci_sync_catalog.sh')], cwd=tmp,
                                    env=env, text=True, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('disposable', result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_concurrent_main_push_rebuilds_instead_of_replaying_stale_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, seed, runner = (root / name for name in ('remote.git', 'seed', 'runner'))
            subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(remote)],
                           check=True, capture_output=True)
            subprocess.run(['git', 'clone', str(remote), str(seed)], check=True, capture_output=True)
            (seed / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/catalog.py', seed / 'scripts/catalog.py')
            (seed / 'tests').mkdir()
            (seed / 'tests/test_generated.py').write_text(
                'import json,unittest\nfrom pathlib import Path\n'
                'class Generated(unittest.TestCase):\n'
                ' def test_count(self):\n'
                '  data=json.loads(Path("templates/catalog.json").read_text())\n'
                '  self.assertEqual(data["template_count"],len(list(Path("templates").rglob("profile.json"))))\n')
            heading = '### 🎬 已收录 [99 个视频模板](templates/) · 持续更新\n'
            (seed / 'README.md').write_text(heading, encoding='utf-8')
            profile = json.loads((ROOT / 'templates/character-short/not-a-sin/profile.json').read_text())
            profile['files'] = {'guide': 'README.md', 'agent_entry': 'SKILL.md'}

            def add_recipe(name):
                folder = seed / 'templates' / name
                folder.mkdir(parents=True)
                (folder / 'README.md').write_text('# Guide')
                (folder / 'SKILL.md').write_text('# Skill')
                profile['id'] = name
                (folder / 'profile.json').write_text(json.dumps(profile))

            add_recipe('first')
            self.commit(seed)
            self.git(seed, 'push', 'origin', 'main')
            subprocess.run(['git', 'clone', str(remote), str(runner)], check=True, capture_output=True)
            add_recipe('second')
            (seed / 'README.md').write_text(heading + '\nConcurrent author text.\n', encoding='utf-8')
            self.commit(seed)
            concurrent_head = self.git(seed, 'rev-parse', 'HEAD').stdout.strip()
            shim = root / 'bin'
            shim.mkdir()
            marker = root / 'injected'
            real_git = shlex.quote(shutil.which('git'))
            (shim / 'git').write_text(
                '#!/usr/bin/env bash\nset -e\n'
                f'if [[ "${{1:-}}" == push && ! -f {shlex.quote(str(marker))} ]]; then\n'
                f'  touch {shlex.quote(str(marker))}\n'
                f'  {real_git} -C {shlex.quote(str(seed))} push origin main\n'
                'fi\n'
                f'exec {real_git} "$@"\n')
            (shim / 'git').chmod(0o755)
            env = {**os.environ, 'GITHUB_ACTIONS': 'true', 'PATH': str(shim) + os.pathsep + os.environ['PATH']}
            result = subprocess.run(['bash', str(ROOT / 'scripts/ci_sync_catalog.sh')], cwd=runner,
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(marker.is_file())
            self.assertIn('rejected', result.stderr)
            self.git(seed, 'fetch', 'origin', 'main')
            parent = self.git(seed, 'rev-parse', 'origin/main^').stdout.strip()
            self.assertEqual(parent, concurrent_head)
            readme = self.git(seed, 'show', 'origin/main:README.md').stdout
            # 首页标题允许带一个临时显示偏移（scripts/catalog.py 的 HEADLINE_COUNT_OFFSET）
            offset = int(re.search(r'HEADLINE_COUNT_OFFSET\s*=\s*(\d+)',
                                   (ROOT / 'scripts/catalog.py').read_text()).group(1))
            self.assertIn(f'[{2 + offset} 个视频模板]', readme)
            self.assertIn('Concurrent author text.', readme)
            data = json.loads(self.git(seed, 'show', 'origin/main:templates/catalog.json').stdout)
            self.assertEqual(data['template_count'], 2)


if __name__ == '__main__':
    unittest.main()
