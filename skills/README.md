# 共用 Skills

按所用工具选择一个 Skill。每个目录可独立使用，包含完整 `SKILL.md` 与配套说明；有脚本的目录需一并保留。

| Skill | 用途 |
| --- | --- |
| [ComfyUI 参考图](comfyui-reference-images/SKILL.md) | SDXL / Anima，默认本地；按需在 Civitai、Hugging Face 查找和核验模型 |
| [GPT Image 2 high](gpt-image2-reference-images/SKILL.md) | 多参考图绑定、角色与场景生成、单次调用和输出恢复 |
| [NovelAI 官方 API](novelai-reference-images/SKILL.md) | 文生图、图生图、提示词与参考功能说明 |
| [角色合集剪辑](character-showcase-editing/SKILL.md) | 图片缩放、纯溶解、图接视频、视频合集与音轨处理 |
| [参考视频获取](reference-video-fetch/SKILL.md) | B 站 / YouTube 匿名取参考视频，不登录、不传 cookie，写出抓取记录 |

## 使用

将所需完整目录安装到 Agent 支持的 Skill 目录，或直接让 Agent 读取对应 `SKILL.md` 并按步骤执行。文件内相对路径以该 Skill 目录为起点；模型、密钥、输入素材和运行结果由用户自己的环境提供。

例如：“使用参考图 Skill，根据我提供的人物图，为这一镜头准备首帧和尾帧，保持服装与场景一致。”

Agent 需要文件、网络或相应生图工具权限；视觉验收还需要看图能力。Skill 本身不提供模型权限、算力或账户额度。

## 验证状态

- ComfyUI：流程与官方资料已核对，未用本包实跑推理；不附带私人风格工作流。
- GPT Image 2 / NovelAI：请求与异常处理通过离线测试，未执行真实付费生成。
- NovelAI：当前模型的完整 API 配置需先核实，高级参考功能尚未纳入附带客户端。
- 参考视频获取：链接校验、竖屏选流、画质上限与失败分类通过离线测试（21 项）；匿名可用画质逐视频不同，用 `--probe` 现场核对，已实测两条 B 站视频。
- 视频模板的完整执行包仍在整理，参考图 Skill 不代表视频流程已可一键运行。
- 角色合集：已提供参数化剪辑执行器及离线计划检查，公开配置未重新渲染；生成链路见各模板。

详见[验证记录](../docs/skill-validation.md)。
