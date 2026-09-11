#!/usr/bin/env python3
"""Build and search recipe indexes from template profile.json files. No network or inference."""
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def normalize(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value).casefold())


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text')
    return value.strip()


def string_list(value, name):
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f'{name} must be a nonempty text list')
    return value


def local_path(folder, value, root):
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError('Index entry paths must be relative')
    path = (folder / value).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError('Index entry points outside its template or to a missing file')
    return path.relative_to(root.resolve()).as_posix()


def collect(root):
    records, ids = [], set()
    for path in sorted(root.rglob('profile.json')):
        folder = path.parent
        data = json.loads(path.read_text(encoding='utf-8'))
        # Declared recipes cannot disappear silently when an entry file is missing.
        if 'index' not in data and not ((folder/'README.md').is_file() and (folder/'SKILL.md').is_file()):
            continue
        if not (folder/'README.md').is_file() or not (folder/'SKILL.md').is_file():
            raise ValueError(f'{path.relative_to(root)} needs README.md and SKILL.md')
        meta = data.get('index')
        if not isinstance(meta, dict):
            raise ValueError(f'{path.relative_to(root)} needs index metadata')
        recipe_id = nonempty(data.get('id'), 'id')
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', recipe_id) or recipe_id in ids:
            raise ValueError('Recipe IDs must be stable, unique lowercase slugs')
        ids.add(recipe_id)
        record = {'id': recipe_id}
        for key in ('title', 'category', 'summary', 'request_example', 'status_label'):
            record[key] = nonempty(meta.get(key), key)
        for key in ('aliases', 'tags', 'customizable', 'requirements'):
            record[key] = string_list(meta.get(key), key)
        record['variants'] = string_list(meta['variants'], 'variants') if 'variants' in meta else []
        record['status'] = nonempty(data.get('status'), 'status')
        files = data.get('files', {})
        record['guide'] = local_path(folder, files.get('guide', 'README.md'), root)
        record['agent_entry'] = local_path(folder, files.get('agent_entry', 'SKILL.md'), root)
        record['profile'] = path.relative_to(root).as_posix()
        records.append(record)
    records.sort(key=lambda item: item['id'])
    return {'schema_version': 1, 'path_base': 'directory containing catalog.json',
            'template_count': len(records), 'templates': records}


def cell(value):
    return value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('|', '&#124;').replace('\n', ' ')


def homepage_count(text, count):
    pattern = r'^### 🎬 已收录 \[\d+ 个视频模板\]\(templates/\) · 持续更新$'
    updated, matches = re.subn(pattern, f'### 🎬 已收录 [{count} 个视频模板](templates/) · 持续更新', text, flags=re.MULTILINE)
    if matches != 1:
        raise ValueError('Homepage must contain exactly one template-count heading linked to templates/.')
    return updated


def markdown(catalog):
    out = ['# 模板索引', '', f"目前收录 **{catalog['template_count']} 个视频模板**。按名称、别名或类型查找，再把一句话需求交给对应 Skill。",
           '', '剧情示例、备用角色素材、参考图 Skill 和空目录不重复计为模板。', '',
           '[给 Agent 的索引](catalog.json) · [搜索与维护说明](../docs/template-index.md)', '']
    categories = sorted({r['category'] for r in catalog['templates']})
    out += ['类型：' + ' · '.join(f'[{cell(name)}](#category-{i})' for i,name in enumerate(categories,1)), '']
    for i,category in enumerate(categories,1):
        out += [f'<a id="category-{i}"></a>', '', f'## {category}', '',
                '| 模板 | 别名 / 标签 | 一句话开始 | 使用状态 |', '| --- | --- | --- | --- |']
        for item in catalog['templates']:
            if item['category'] != category: continue
            out.append(f"| [{cell(item['title'])}]({item['guide']}) · [执行]({item['agent_entry']}) | {cell('、'.join(item['aliases'] + item['tags']))} | {cell(item['request_example'])} | {cell(item['status_label'])} |")
        out.append('')
    out += ['## 快速查找', '', '网页中可用查找功能搜索上表的名称或别名；本地也可运行：', '', '```bash',
            'python3 scripts/catalog.py search "不是罪过"',
            'python3 scripts/catalog.py search "Ave Mujica" --json',
            'python3 scripts/catalog.py search --tag 舞蹈', '```', '',
            '命令从仓库根目录运行。指定角色与图片优先，备用素材不作为模板分类。各项实际依赖以模板说明为准。', '',
            '目录由各模板的 `profile.json` 自动生成；新增模板后运行 `python3 scripts/catalog.py build`。', '']
    return '\n'.join(out)


def search(catalog, query='', tags=()):
    terms = [normalize(part) for part in query.split() if normalize(part)]
    wanted = [normalize(tag) for tag in tags]
    results = []
    for record in catalog['templates']:
        field = normalize(' '.join([record['id'], record['title'], record['category'], record['summary'],
                                   *record['aliases'], *record['tags'], *record['customizable']]))
        if all(word in field for word in terms) and all(tag in {normalize(t) for t in record['tags']} for tag in wanted):
            results.append(record)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('build', help='Regenerate the Markdown directory and JSON catalog')
    commands.add_parser('check', help='Fail if generated indexes are stale or profiles invalid')
    query = commands.add_parser('search', help='Search titles, aliases, descriptions and tags without network access')
    query.add_argument('query', nargs='?', default='')
    query.add_argument('--tag', action='append', default=[])
    query.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        root = ROOT/'templates'
        catalog = collect(root)
        if args.command == 'search':
            results = search(catalog, args.query, args.tag)
            if args.json:
                print(json.dumps({'count': len(results), 'path_base': 'templates/', 'templates': results}, ensure_ascii=False, indent=2))
            elif results:
                for item in results:
                    print(f"{item['title']} | {item['status_label']}\n  Agent: templates/{item['agent_entry']}")
            else:
                print('没有匹配的模板。试试别名或标签；不要自动替换为其他题材。')
            return 0
        outputs = {root/'catalog.json': json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', root/'README.md': markdown(catalog)}
        homepage = ROOT/'README.md'
        outputs[homepage] = homepage_count(homepage.read_text(encoding='utf-8'), catalog['template_count'])
        if args.command == 'check':
            if any(not path.is_file() or path.read_text(encoding='utf-8') != text for path,text in outputs.items()):
                raise ValueError('Template indexes are stale; run python3 scripts/catalog.py build')
            print(f"索引有效：{catalog['template_count']} 个模板。")
        else:
            for path,text in outputs.items():path.write_text(text, encoding='utf-8')
            print(f"已生成索引：{catalog['template_count']} 个模板。")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('Index error: '+str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
