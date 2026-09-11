# Video ReGen Recipes

**一句话，让 Agent 在本地复刻热点 MEME／鬼畜／手书视频，也可在 Updream 等线上工具快速复用。**

### 🎬 已收录 [8 个视频模板](templates/) · 持续更新

![Video ReGen Recipes 封面](assets/hero.png)

本仓库搜集各类二创模板，旨在降低短视频制作门槛。通过可复用的模板与 Skills，教会你的 Agent 部署和调用本地视频工作流，串联参考图、声音、视频生成与后期剪辑，让你用一句话开始创作属于自己的版本。

## 怎么用

**[选模板](templates/) → 准备素材 → 生成视频 → 剪辑成片。**

- **Agent 入口**：可让 Codex、Claude Code、Hermes Agent、OpenClaw 等支持 Skills 的 Agent 读取模板，见[使用与适配状态](docs/agent-compatibility.md)。
- **视频生成**：聚焦 ComfyUI + MiniMax H3，默认使用[本地 ComfyUI](docs/comfyui-local.md)，也可连接[远程服务器](docs/comfyui-remote.md)。
- **图片与声音**：工具不限，可使用 ComfyUI、NovelAI、GPT Image、语音服务或已有素材。

[参考图 Skills](skills/) 可独立使用；视频模板的完整执行包仍在整理，各项验证状态见对应说明。

## TODO

- [x] 收录视频模板，提供分类与关键词索引
- [x] 整理从素材生成到后期剪辑的 Skills 与工具
- [ ] 适配 Updream、Runway 等工具的 Computer Use 操作
- [ ] 逐一完成各模板的 Windows 端测试
- [ ] 适配更多 Agent 产品，如 Trae、WorkBuddy

## 参与贡献

欢迎分享视频案例、提示词、工作流和复现经验，见[贡献指南](CONTRIBUTING.md)。

[模板怎么写](docs/template-format.md) · [ComfyUI 工作流库](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit) · [H3 制作流程](docs/local-h3.md) · [图片与声音](docs/assets-and-audio.md)

## 使用责任声明

使用者应确保所用素材及生成、传播的内容符合法律法规与公序良俗，不侵犯他人合法权益。因使用者违法、侵权或不当使用本项目产生的责任，由使用者依法承担，本项目作者及维护者不承担相应责任。

## 许可

原创代码与文档采用 [MIT License](LICENSE)。模型和第三方素材遵循各自许可。

<a href="https://space.bilibili.com/12595237"><img src="assets/icons/bilibili.svg" width="20" height="20" alt="Bilibili logo"> Bilibili</a> · <a href="https://www.xiaohongshu.com/user/profile/68483ecb000000001b019555"><img src="assets/icons/xiaohongshu.svg" width="20" height="20" alt="Rednote logo"> Rednote / 小红书</a> · <a href="https://civitai.red/user/Shenrui_Ma"><img src="assets/icons/civitai.ico" width="20" height="20" alt="Civitai logo"> Civitai / C站</a>
