# 模板索引

目前收录 **4 个视频模板**。按名称、别名或类型查找，再把一句话需求交给对应 Skill。

剧情示例、备用角色素材、参考图 Skill 和空目录不重复计为模板。

[给 Agent 的索引](catalog.json) · [搜索与维护说明](../docs/template-index.md)

类型：[番剧对白与叙事场景](#category-1) · [绘制过程与对比视频](#category-2) · [角色主题短片](#category-3)

<a id="category-1"></a>

## 番剧对白与叙事场景

| 模板 | 别名 / 标签 | 一句话开始 | 使用状态 |
| --- | --- | --- | --- |
| [MyGO / Ave Mujica AI 番剧](anime-dialogue-scene/mygo-ave-mujica/README.md) · [执行](anime-dialogue-scene/mygo-ave-mujica/SKILL.md) | MyGO、MyGO!!!!!、Ave Mujica、Mujica、少女乐队AI番剧、少女乐队、剧情、多人对白、番剧 | 做一集 MyGO 或 Ave Mujica 短篇，剧情是……。 | 构建与执行工具已提供；新环境待实测 |

<a id="category-2"></a>

## 绘制过程与对比视频

| 模板 | 别名 / 标签 | 一句话开始 | 使用状态 |
| --- | --- | --- | --- |
| [基于大模型的SVG临摹重绘](drawing-process/svg-redraw-comparison/README.md) · [执行](drawing-process/svg-redraw-comparison/SKILL.md) | SVG临摹、SVG重绘、SVG绘画过程、GPT6画图、原图对比、SVG、临摹、绘画过程、对比视频 | 把这张图临摹成SVG，导出原图与绘制过程的对比视频。 | 纯SVG Demo与40秒对比视频已导出；非逐像素零误差 |

<a id="category-3"></a>

## 角色主题短片

| 模板 | 别名 / 标签 | 一句话开始 | 使用状态 |
| --- | --- | --- | --- |
| [一点一滴刺痛我的心](character-short/bit-by-bit-heartache/README.md) · [执行](character-short/bit-by-bit-heartache/SKILL.md) | 一滴一滴刺痛我的心、刺痛我的心、Bit by Bit Heartache、动作重演、舞蹈、音乐短片 | 用我喜欢的角色，做一支《一点一滴刺痛我的心》。 | 已有片段可重剪；新角色需配置续接 |
| [XX不是罪过](character-short/not-a-sin/README.md) · [执行](character-short/not-a-sin/SKILL.md) | 不是罪过、XX不是罪、Not a Sin、动作重演、舞蹈、音乐短片 | 用我喜欢的角色，做一支《XX不是罪过》。 | 说明已整理；续接执行包待完善 |

## 快速查找

网页中可用查找功能搜索上表的名称或别名；本地也可运行：

```bash
python3 scripts/catalog.py search "不是罪过"
python3 scripts/catalog.py search "Ave Mujica" --json
python3 scripts/catalog.py search --tag 舞蹈
```

命令从仓库根目录运行。指定角色与图片优先，备用素材不作为模板分类。各项实际依赖以模板说明为准。

目录由各模板的 `profile.json` 自动生成；新增模板后运行 `python3 scripts/catalog.py build`。
