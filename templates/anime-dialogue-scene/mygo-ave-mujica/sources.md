# 来源与许可

原创模板与制作设计：**Shenrui Ma（四倍体果蝇）**。

本模板根据贡献者提供的 2026-09-10 MyGO 制作指南整理，提取独立 Ref2VA 分段、角色与声音映射、字幕对齐和后期方法。内部指南、原始素材、任务记录和个人环境均未随仓库公开；原指南报告的实测与本次离线验证分别列在[验证记录](evidence/README.md)。

两份剧情示例是本仓库新写的同人练习，不复述官方剧情或复制官方对白。Ave Mujica 沿用同一制作流程准备新资产，尚无本包实测成片。

## 作品与角色资料

- [BanG Dream! It's MyGO!!!!! 官方人物目录](https://anime.bang-dream.com/mygo/character/)
- [BanG Dream! Ave Mujica 官方人物目录](https://anime.bang-dream.com/avemujica/character/)
- [Ave Mujica 官方角色与演员名单](https://anime.bang-dream.com/avemujica/staff-cast/)

从人物页及其链接的官方频道核对资产来源。网页资源会更新，模板不固定角色图片下载地址；获取后在用户项目中保存来源、版本与哈希。

## 生成与后期依据

- [MiniMax H3 模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)及[官方提示词规范](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing)
- [ComfyUI API](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)与[WhisperX](https://github.com/m-bain/whisperX)
- [pymss 2.0.14 发布说明](https://pypi.org/project/pymss/2.0.14/)与[历史分离模型来源](https://huggingface.co/baicai1145/pymss)
- [FFmpeg 滤镜文档](https://ffmpeg.org/ffmpeg-filters.html)
- 原制作记录注明曾参考[分镜、音频、风格与提示词教程](https://www.bilibili.com/video/BV1gTbW6oEUh/)。本次未重新观看，不把其建议当作本包已运行的节点。

模型、量化版本、第三方节点和音源按各自许可证使用。仓库 MIT 许可只覆盖本仓库原创代码与说明，不包含角色 IP、图片、PV、录音、模型权重或第三方代码。发布成片时标明非官方 AI 同人作品，生成的新台词不代表官方剧情或演员本人发言。
