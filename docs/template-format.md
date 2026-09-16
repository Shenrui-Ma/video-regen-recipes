# 模板格式

以下是建议结构，不要求固定执行器。历史成片、文档收录、执行包可运行与新角色复现分别标注。

```text
templates/<template-id>/
├── README.md     # 效果、素材、步骤、可改范围
├── sources.md    # 作者、参考链接与许可
├── prompts/      # 原提示词与实际提交稿
├── workflows/    # 本地 H3 工作流或固定版本引用
├── assets/       # 可公开的小型素材
└── evidence/     # 配置、结果与失败修复
```

## 最少写清五件事

1. **效果**：保留什么拍法，用户可以改什么。
2. **素材**：图片和声音的要求、用途、文件绑定；工具可本地或在线。写清每份素材属于自有、公开可校验下载，还是需要用户手动下载（登录墙、网盘）；后一类按[图片与声音](assets-and-audio.md)交回用户，不要代下。
3. **步骤**：从素材准备到 H3 生成、选片与剪辑，怎样局部返修。
4. **配置**：硬件、模型权重、节点版本、工作流和实际参数，参考[H3 说明](local-h3.md)。
5. **实测**：日期、输入、输出、实际时长、耗时、返工与已知限制。

镜头、生成任务和剪辑片段分别编号并记录对应关系，便于只重做受影响的部分。
标明“整理中”“已验证配置”或“待修复”；“已验证”只指实际跑过的环境与输入。
ComfyUI 默认按[本地方式](comfyui-local.md)使用，[远程方式](comfyui-remote.md)单独处理连接与文件传输；模板不写死服务地址或机器路径。
共用内容引用仓库的[共用 Skills](../skills/)与外部 [ComfyUI Toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)（按固定 revision + 文件哈希引用），不必复制进模板；模型与素材按[图片与声音](assets-and-audio.md)获取。仓库根目录的 `shared/` 与 `workflows/comfyui/h3/` 目前只是占位目录，实际共用内容以上述两处为准。一个充分验证的配置即可提交。

## 交付契约（每个模板都要满足）

目录至少包含：`README.md`、`SKILL.md`、`profile.json`、`sources.md`、`LICENSE`、`LICENSES.md`、`references/validation.md`。

`SKILL.md` 前置字段写全 `name`、`description`、`version`、`author`、`license`、`platforms`，其中 `version` 与 `profile.json` 保持一致。`LICENSE` 是本模板的许可副本（原创代码与文档沿用仓库 MIT），`LICENSES.md` 逐项列出第三方组件、权重、字体与素材的条款边界。

`profile.json.runtime` 记录**运行事实**，让 Agent 在开工前就能判断“能不能跑、跑到哪一步验证过”：

| 字段 | 含义 |
| --- | --- |
| `distribution_mode` | `portable-*` = 可独立分发，目录内不得引用模板之外的任何路径（参考 heartache）；`repo-bound` = 仓库内模板，可引用 `skills/`、`docs/` 与同级模板 |
| `entry` | 可执行入口脚本；没有就写 `null` |
| `asset_manifest` | 运行必需素材清单（路径 + 字节 + SHA-256）；没有就写 `null` |
| `environment_lock` | 环境或工作流的固定版本记录；没有就写 `null` |
| `existing_environment_verified` | 是否在某个可用环境里真实产出过（历史案例算，没跑过就 false） |
| `clean_install_inference_verified` | 干净安装后是否跑通推理；没跑就如实写 false |

`repo-bound` 模板引用了 `skills/`、`docs/` 或同级模板时，必须在 `profile.json.requires` 的 `skills` / `docs` / `templates` 中声明。`tests/test_template_contract.py` 会校验目录齐全、前置字段、runtime 字段、链接可解析、外部依赖已声明，以及依赖路径真实存在。

`references/validation.md` 写清三件事：已验证什么（含证据位置）、未验证什么（并给出两个 runtime 旗标的依据）、使用者机器仍需完成什么。不要把“整理时核对过文件”写成“已复现”。

## 加入索引

为 `profile.json` 填写 `index` 信息后，运行 `python3 scripts/catalog.py build` 和 `python3 scripts/catalog.py check`；详细字段见[索引说明](template-index.md)。
