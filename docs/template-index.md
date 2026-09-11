# 查找模板

[浏览目录](../templates/README.md)适合找名称和看用途；[catalog.json](../templates/catalog.json)适合 Agent 读取。两者由每个模板的 `profile.json` 生成。

## 用户入口

说出模板名、梗名或别名，例如“不是罪过”“一滴一滴刺痛我的心”“Ave Mujica”。查找命令从仓库根目录运行：

```bash
python3 scripts/catalog.py search "不是罪过"
python3 scripts/catalog.py search "Ave Mujica" --json
python3 scripts/catalog.py search --tag 舞蹈
```

关键词匹配不区分英文大小写，忽略空格和标点差异；空格分隔的多个词需要同时匹配。多个 `--tag` 也取交集。不填关键词或标签时列出全部模板。

## Agent 路由

1. 先读 `templates/catalog.json`，按 `title`、`aliases`、`tags` 和 `summary` 匹配需求。不要先读取所有模板的长文档。
2. 用户已明确模板名时直接选中；有多个合理候选时展示简短区别，必要时只问一个选择问题。没找到就说明未收录，不用相近名称强行替代。
3. 根据 `requirements` 和 `status_label` 检查是否具备执行条件。索引命中不代表执行包或环境已经准备好。
4. 读取选中条目的 `agent_entry`，再按其流程准备角色、调用工具、生成和剪辑。JSON中的路径相对 `catalog.json` 所在目录；CLI JSON结果中的路径相对 `templates/`。
5. MyGO 与 Ave Mujica 是同一模板的两个剧情入口，按用户选择使用对应示例。备用角色不覆盖用户的角色要求。
6. 角色图像合集与角色视频合集是两个通用入口；指定“泳装动态立绘”时优先选对应子模板，再按其引用加载通用视频流程。子模板有独立镜头、节奏与执行入口，可单独索引；单纯换角色素材不新增模板。

## 新增模板

在已有 `profile.json` 中增加 `index` 对象，包含：

- `title`、`aliases`：显示名称与常见别名。
- `category`、`tags`：成片类型与便于查找的主题。
- `summary`、`customizable`、`request_example`：效果、可改范围与一句话示例。
- `requirements`、`status_label`：必要工具与简短可用状态。
- `variants`：可选，表示同一模板的不同入口，不增加模板计数。

沿用顶层稳定 `id`、`status` 和 `files.guide` / `files.agent_entry`。重命名标题时保留 ID，并把旧名称加入别名。可参考任一已收录模板的实际字段。

```bash
python3 scripts/catalog.py build
python3 scripts/catalog.py check
```

提交时一起更新生成的目录与 JSON。检查会拒绝重复 ID、缺少索引信息、无效入口以及未更新的生成文件。只有同时具备 `profile.json`、`README.md` 和 `SKILL.md` 的目录计为模板；空分类、媒体文件和辅助工具不计入。
