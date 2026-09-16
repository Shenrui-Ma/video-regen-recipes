# 作者与技术来源

原创配方：**Shenrui Ma（四倍体果蝇）**，由 Agent 协助执行与整理。

本配方的制作设计包括角色参考准备、RIFE 半速驱动、本地 H3 音视频续接、精确恢复帧时间线、音乐回装与后期交付。视频生成只使用本文档中的本地／自托管 H3 链路。

## 使用的底层工具

- [MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3) · [模型卡与许可](https://huggingface.co/MiniMaxAI/MiniMax-H3) · [提示词规范](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing)
- [ComfyUI](https://github.com/Comfy-Org/ComfyUI)、[RIFE](https://github.com/hzwer/ECCV2022-RIFE)、[FFmpeg](https://ffmpeg.org/)
- NVIDIA RTX VSR：可选视频增强；实际实现和版本由运行环境决定。

## 参考视频（示例）

- 《🐋DeepSeek不是罪过~🐋》 · 作者：**uulumine゛** · [B 站 BV1LQ7j6WEyD](https://www.bilibili.com/video/BV1LQ7j6WEyD/) · 56.0 秒 · 2026-06-26 投稿。
- 这是第三方作品，仅作为动作与节奏参考：用户应当换成自己的参考视频或自备文件。本仓库不分发它，也不因为引用而获得任何授权。
- 获取方式见[参考视频获取 Skill](../../../skills/reference-video-fetch/SKILL.md)：匿名 `--probe` 实测该条可用画质为 1080p30；抓取文件只留用户本机，配套 `<视频ID>.mp4.fetch.json` 记录链接、作者、时长与哈希。

用户项目的驱动视频、音乐与角色资产分别记录来源与使用范围，不随本仓库分发。仓库 MIT 许可覆盖原创代码与说明，不覆盖角色 IP、输入素材、模型权重或第三方代码。
