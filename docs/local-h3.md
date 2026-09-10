# 本地 H3 模板的执行边界

Video ReGen Recipes 当前整理本地或自托管 ComfyUI／MiniMax H3 视频推理方案。此文说明模板需要交代的条件；当前仓库尚未提供可直接运行的制作模板或安装脚本。

## 本地视频生成，辅助模态自由选择

H3 视频推理可以运行在个人电脑或自己控制的 GPU 服务器。参考图可以来自 ComfyUI、NovelAI、GPT Image、手绘或授权素材；声音可以来自本地 TTS、在线语音服务或授权录音。

采用远程 Agent、在线生图或语音 API 时，整个流程不等于完全离线。模板应说明素材在哪准备、哪些内容会传到外部服务，以及 H3 实际运行在哪里。

## 固定一份可复核配置

每个模板应记录：

- 操作系统、GPU／显存和系统内存。
- ComfyUI 版本、自定义节点来源与版本。
- H3 模式、权重来源与哈希、量化或精度。
- 文本编码器、视频与音频 VAE、可选 LoRA。
- 采样方法、调度器、步数、随机种子与加速选项。
- 实际分辨率、帧数、帧率、生成时长和输出音轨。

显存和速度依据该配置的实测说明。不要把另一种权重、精度或分辨率的结果套用过来。

## 选择模式并检查输入

官方 H3-Base 区分首尾帧类与多模态参考类模型。选择适合的模型和条件节点，明确每张图用于身份、场景、姿态或实际关键帧。音频也要明确是参考音色、参考节奏还是复用信号。

GUI 整合图可能包含被旁路的分支、旧控件值和外部素材路径。提交前沿有效输出链检查真正使用的输入，再导出、校验 API 工作流。仅有节点之间的画布连线，不足以证明首尾帧或音频已经生效。

## 记录任务与结果

建议通过 ComfyUI 的任务接口提交，保存任务 ID、输入配置、输出位置和结果状态。连接中断时先查队列与历史，避免重复生成。

目标时长、帧网格计算后的长度和实际解码时长分别记录。完成后检查人物、动作、画风、音轨和衔接，再进行剪辑或超分。

## 本地 Base 与托管增强

官方资料将 H3-Base、本地之外的 Context-IR 预处理和 Regenerate-2K 区分。若配方调用官方托管预处理或增强，应明确标为混合流程；通用超分后的尺寸也不能标为 H3 原生同规格生成。

模型采用独立 Community License，使用与分发前查看原文；本仓库的 MIT 许可不覆盖模型权重。

## 官方资料

- [MiniMax H3 模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)
- [MiniMax H3 官方代码与 Skills](https://github.com/MiniMax-AI/MiniMax-H3)
- [ComfyUI H3 指南](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)
- [ComfyUI 服务接口](https://docs.comfy.org/development/comfyui-server/comms_routes)
- [H3 模型许可](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE)

以上链接用于确认实际版本与条件，不代表本仓库已经完成其全部能力的复现。

