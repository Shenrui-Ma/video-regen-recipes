"""Repository-wide contract for every template directory.

Two distribution tiers are allowed:

- ``portable-*``: the template can be handed over on its own, so nothing inside it
  may point outside its own directory. heartache is the reference for this tier.
- ``repo-bound``: the template may reference the shared ``skills/`` and ``docs/``
  trees (and sibling templates), but every such dependency has to be declared in
  ``profile.json.requires`` so an agent can see what it needs before starting.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
REQUIRED_FILES = ("README.md", "SKILL.md", "profile.json", "sources.md", "LICENSE", "LICENSES.md")
FRONT_MATTER_FIELDS = ("name:", "description:", "version:", "author:", "license:", "platforms:")
ALLOWED_ESCAPE_ROOTS = ("skills", "docs", "templates")


def template_dirs():
    return sorted(p for p in TEMPLATES.rglob("*") if p.is_dir() and (p / "profile.json").is_file())


def relative_links(text):
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if "://" in target or target.startswith("#") or target.startswith("mailto:"):
            continue
        yield target.split("#")[0]


class TemplateContractTests(unittest.TestCase):
    def test_every_template_ships_the_same_core_files(self):
        for template in template_dirs():
            for name in REQUIRED_FILES:
                self.assertTrue((template / name).is_file(), f"{template.name} 缺少 {name}")
            self.assertTrue((template / "references" / "validation.md").is_file(),
                            f"{template.name} 缺少 references/validation.md")

    def test_skill_front_matter_declares_identity_and_platforms(self):
        for template in template_dirs():
            text = (template / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), f"{template.name} 的 SKILL.md 缺少前置字段")
            front = text.split("---", 2)[1]
            for field in FRONT_MATTER_FIELDS:
                self.assertIn(field, front, f"{template.name} 的 SKILL.md 缺少 {field}")
            profile = json.loads((template / "profile.json").read_text(encoding="utf-8"))
            version = re.search(r"^version:\s*(.+?)\s*$", front, flags=re.MULTILINE)
            self.assertIsNotNone(version, f"{template.name} 的 SKILL.md version 无法解析")
            self.assertEqual(version.group(1).strip('"\''), str(profile.get("version")),
                             f"{template.name} 的 SKILL version 与 profile.json 不一致")

    def test_profile_runtime_is_present_and_honest(self):
        for template in template_dirs():
            profile = json.loads((template / "profile.json").read_text(encoding="utf-8"))
            runtime = profile.get("runtime")
            self.assertIsInstance(runtime, dict, f"{template.name} 的 runtime 必须是对象")
            mode = runtime.get("distribution_mode")
            self.assertIsInstance(mode, str, f"{template.name} 缺少 runtime.distribution_mode")
            self.assertTrue(mode.startswith(("portable-", "repo-bound")),
                            f"{template.name} 的 distribution_mode 不在约定范围内：{mode}")
            for flag in ("clean_install_inference_verified", "existing_environment_verified"):
                self.assertIsInstance(runtime.get(flag), bool,
                                      f"{template.name} 缺少布尔 {flag}")
            for key in ("entry", "asset_manifest", "environment_lock"):
                value = runtime.get(key)
                if value:
                    self.assertTrue((template / value).exists(),
                                    f"{template.name} 的 runtime.{key} 指向不存在的文件：{value}")

    def test_markdown_links_resolve_and_declared_dependencies_cover_escapes(self):
        for template in template_dirs():
            profile = json.loads((template / "profile.json").read_text(encoding="utf-8"))
            runtime = profile["runtime"]
            declared = []
            for group in ("skills", "docs", "templates"):
                values = (profile.get("requires") or {}).get(group, [])
                self.assertIsInstance(values, list, f"{template.name} 的 requires.{group} 必须是数组")
                declared.extend(values)
            portable = runtime["distribution_mode"].startswith("portable-")
            for page in sorted(template.rglob("*.md")):
                for target in relative_links(page.read_text(encoding="utf-8")):
                    resolved = (page.parent / target).resolve()
                    where = f"{page.relative_to(template)} -> {target}"
                    if resolved.is_relative_to(template.resolve()):
                        self.assertTrue(resolved.exists(), f"{template.name} 断链：{where}")
                        continue
                    self.assertTrue(resolved.exists(), f"{template.name} 外部引用不存在：{where}")
                    relative = resolved.relative_to(ROOT).as_posix()
                    if portable:
                        self.fail(f"{template.name} 声明为可独立分发，却引用了模板之外：{where}")
                    self.assertIn(relative.split("/")[0], ALLOWED_ESCAPE_ROOTS,
                                  f"{template.name} 引用了仓库外的共享层：{where}")
                    covered = any(relative == item or relative.startswith(item.rstrip("/") + "/")
                                  for item in declared)
                    self.assertTrue(covered,
                                    f"{template.name} 的外部依赖未在 profile.json.requires 声明：{relative}")

    def test_declared_dependencies_exist(self):
        for template in template_dirs():
            profile = json.loads((template / "profile.json").read_text(encoding="utf-8"))
            for group in ("skills", "docs", "templates"):
                for item in (profile.get("requires") or {}).get(group, []):
                    self.assertTrue((ROOT / item).exists(),
                                    f"{template.name} 声明的依赖不存在：{item}")


if __name__ == "__main__":
    unittest.main()
