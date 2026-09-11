# Agent 使用与适配状态

本仓库使用 `SKILL.md` 组织指令、脚本与素材。支持 Skills 的产品可以作为入口，但能够读取指令不代表每个视频模板都已在该产品中跑通。

| Agent | 使用入口 | 本仓库验证范围 |
| --- | --- | --- |
| [Codex](https://developers.openai.com/codex/skills/) | 在仓库工作区读取对应 `SKILL.md` | 有开发、离线检查及部分媒体制作记录；未逐模板完成生成实测 |
| [Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) | 读取模板，或按官方方式安装 Skill | 多个模板来自实际制作记录；公开适配版仍需按模板核对 |
| [Claude Code](https://code.claude.com/docs/en/skills) | 读取模板，或按官方方式安装 Skill | Skill 格式可作为接入方式；本仓库尚未完成端到端实测 |
| [OpenClaw](https://docs.openclaw.ai/tools/skills) | 读取模板，或按官方方式安装 Skill | Skill 格式可作为接入方式；本仓库尚未完成端到端实测 |

最直接的方式：下载完整仓库，让 Agent 读取 `templates/catalog.json`，找到所选模板的 `SKILL.md` 后按步骤执行。不要只复制一个 Markdown 文件；模板可能引用共用 Skills、配套脚本或固定版本工作流，需保留目录关系。

Agent 需要能够读写项目文件、运行相应脚本、访问用户自己的 ComfyUI/API；需要操作网页时还需相应浏览器工具。模型、算力、账户权限与执行环境由用户提供，具体要求见模板。仅能聊天、没有执行工具的接入方式无法自动完成本地视频制作。

后续计划：逐模板补充 Windows 与各 Agent 的实测记录，并扩展 Trae、WorkBuddy 等产品。记录应包含产品版本、系统、实际执行范围和失败恢复结果；未测试项不标为已兼容。

以上入口依据各产品官方 Skill 文档于 2026-09-12 核对；具体发现目录、安装方式和权限以所用版本为准。
