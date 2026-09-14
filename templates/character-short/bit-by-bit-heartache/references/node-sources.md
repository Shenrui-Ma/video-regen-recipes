# 节点来源：历史记录与当前公开环境

**本页及 [node-sources.json](node-sources.json) 的 `node_sources` 是历史恢复图的来源记录，不是当前安装清单。当前运行图由 [workflow.lock.json](workflow.lock.json) 锁定到 toolkit 的 Core 续接包，其依赖以 [环境依赖锁](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/dependencies.lock.json) 为准，安装与验收见 [环境说明](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/README.md)。**

## 当前公开链路

当前 H3 首段/续段合计需要 22 类节点：21 类 ComfyUI Core，1 类公开自定义节点 `MiniMaxH3MotionContext`。不依赖作者私有 `HermesH3Continuation`，不要求公开安装历史 Save/Load/Trim 包。

- 保存：Core `LTXVSeparateAVLatent` 将采样器联合 AV latent 拆成视频与音频两路，各用 Core `SaveLatent` 保存。
- 续接：两路 Core `LoadLatent` 读回，由 `LTXVConcatAVLatent` 重组后送入 `MiniMaxH3MotionContext.context_latent`。不能只保存视频 latent 或用末帧代替联合 AV 续接。
- 裁切：当前图及运行层负责发布帧/音频裁切，不调用历史 `TrimMiniMaxH3MotionContext`。这是当前公开替代实现，非历史私有缓存格式的字节等价承诺。
- 唯一自定义包为 [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)，固定 commit `f80e36bc1d7887a143b12e6645313fd6b9cd2aee`，GPL-3.0。`H3MotionContextOfficial` 只是目录名，不表示官方 Core。
- Core 固定 commit `6f7cd7fceaaf60d2669b554936394a7412c6fde5`。公开安装计划、Python wheel 全闭包、模型 URL/哈希、motion-context 与 comfy-kitchen INT8 补丁均已在当前锁记录；不要使用浮动上游版本或旧文档的共享目录安装命令。
- 源码补丁、环境 CPU 测试和现有服务只读 schema 已检查；干净 Linux 安装和本次 GPU 推理未执行。当前锁不是历史运行环境锁，也不是任意 GPU/片段尺寸的兼容性保证。

不安装 Sage 私有 wrapper，不默认改变注意力实现或加节点白名单。参考图是已有输入：用户传图直接用，未传图查官方立绘；原爻光图片的历史制作来源不转化为当前生图模型/节点依赖。

## 历史恢复图来源（仅溯源）

历史恢复图曾有 20 类节点：16 类 Core，4 类非 Core，分属两个包。该计数不再描述当前工作流。JSON 保留逐类历史映射，便于识别旧图，不表示仍待用户安装它们。

1. `MiniMaxH3MotionContext`：上述公开包。历史核查的 checkout 有本地 `nodes.py` 修改；现在已随 Toolkit `environments/h3/vendor/motion-context/payload-before-audio.patch` 发布固定 before/after 源码、哈希和许可。仍不把当前补丁基底认定为当年运行锁。
2. `SaveMiniMaxH3AVLatent`、`LoadMiniMaxH3AVLatent`、`TrimMiniMaxH3MotionContext`：历史作者本地 `HermesH3Continuation/__init__.py`，源码 SHA-256 `edf270a641808282f5d3ff51a260518821a59ad1dffcd27e23e6f6794787c573`。没有独立公开发行包或已确认的软件许可，仓库与许可在 JSON 保留 null。当前图已移除依赖，不发布私有源码，也不要求复现者搜索同名节点。

## Core 模块归属

加载器/latent 文件读写主要在 `nodes`；采样在 `comfy_extras.nodes_custom_sampler`；联合 AV 拆分/合并在 `comfy_extras.nodes_lt`；画面批次裁切在 `comfy_extras.nodes_images`；音频解码在 `comfy_extras.nodes_audio`；视频读写在 `comfy_extras.nodes_video`；H3 参考生成在 `comfy_extras.nodes_minimax_h3`。逐类当前来源与端口 contract 见当前锁及 Toolkit `environments/h3/vendor/audit/object-info.contract.json`；该 contract 不含服务用户文件枚举。
