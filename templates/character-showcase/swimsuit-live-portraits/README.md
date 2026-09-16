# 泳装动态立绘视频集

**一句话，用喜欢的角色制作一支泳装动态立绘合集。**

> 用我指定的角色，做一支约一分钟的泳装动态立绘视频集：从 ComfyUI 生成首帧，再用本地 H3 做动态视频，保留水声，配上我提供的音乐。

Agent 会准备 8 张首帧、生成对应片段，再按模板剪成竖屏合集。可换角色、泳装、海边或泳池场景、动作和音乐；也可以直接提供自己的首帧。未提供音乐时保留自然声。

需要：可调用 Skill 的 Agent、本地 ComfyUI 和 MiniMax H3、Python + Pillow、FFmpeg。参考图模型会按角色需求匹配；远程 ComfyUI 走独立连接配置。具体工作流由 [ComfyUI Toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit) 提供。

- [让 Agent 执行](SKILL.md)
- [8 段分镜与替换方法](references/shot-plan.md)
- [首帧生成与 H3 参数](references/generation.md)
- [真实案例与验证边界](references/evidence.md)

**配方：Shenrui Ma（四倍体果蝇）**

## 配套资源

- [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)：`h3-i2v-live-portrait` 等固定版本工作流，固定 revision 与哈希见 [workflows/toolkit-source.json](workflows/toolkit-source.json)
- [Shenrui-Ma/video-regen-assets](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets)：公开素材库；本模板不附带媒体

第三方组件与素材条款见 [LICENSES.md](LICENSES.md)，本次验证范围见 [验证记录](references/validation.md)，来源与署名见 [sources.md](sources.md)。
