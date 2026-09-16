---
name: character-rvc-training-cover
description: 为用户指定角色发现与核验语音来源，整理授权录音和分组留出集，在固定 RVC v2/48k/F0 环境训练与选择模型、校验 added 索引，再分声部转换歌曲并混音交付；莫斯提马中文若舞仅为历史示例。
version: 0.1.0
author: Shenrui Ma（四倍体果蝇）
license: "See LICENSES.md for component terms"
platforms: [linux]
---

# 指定角色 RVC 训练与翻唱

## 1. 先发现来源，再补齐缺口

读 [README](README.md)、[profile](profile.json)、[sources](sources.md) 和[来源发现协议](references/discovery.md)。尊重用户指定角色、作品、语言和 CV；不要用历史莫斯提马或另一角色替换。先用 Agent 原生网页搜索官方/可信角色资料与语音，核对身份、语言和配音，再用 `scripts/discover.py` 的 yt-dlp 内建元数据搜索兜底；只有仍无可用来源才问用户补充，不能早早把搜集工作全部交回用户。

发现脚本接口：`--character --series --language --actor(可选) --provider bilibili|youtube|both --output 新JSON`，另支持重复 `--alias`、`--limit 1..10`、`--timeout 10..180`、`--inspect-url` 和 `--yt-dlp`。只搜元数据不下载，返回的是候选，不自动认定为官方或已获授权；它不是全网官方来源验证器。URL-only flat 候选用 inspect 补详情，搜索错误与真正无结果分别处理，不能把 412 或工具缺失当作角色无语音。读取来源页的逐项判断字段；身份匹配和权利许可是不同判断。已知角色仍可能有中日配等不同声线，不能仅以角色名配对。

建立新 job ID。权利状态保持 `unknown` / `pending-review`，直到取得本次具体依据；不要用一组 `true` 值代替授权书或继承旧用途字段。若身份明确而权限未明，可完成发现和计划，停在素材取得/训练之前，不因“先搜”越过权利边界。

## 2. 固定环境与输入

按[部署](references/deployment.md)固定官方 commit `4338f12c3c28c80b3ac015e2d0df66c41592746d`，使用原拼写 `requirments_cu118_py312.txt` 与 HF 格式 `assets/hubert_base/`，不能换成旧 `.pt`。读取 [model-catalog/dependencies.json](model-catalog/dependencies.json)，核对字节与可信来源；训练不需要 DDSP 权重。环境、下载和 GPU 分配均独立记录。用户指定远程主机时使用其已配置连接部署和取回，本机可只负责控制；不要猜主机、认证或 GPU 编号，也不要在 Mac 上把这条 CUDA 训练路线说成 MPS 已适配。

阶段开始前用 `run_guard.py snapshot` 冻结本次真实输入/参数；每次恢复和下游启动前 `check`。目录快照包括成员增加/删除和内容哈希，不能只凭 `.done`、mtime 或输出文件名跳过。helper 不是调度器，不会证明作业完成；只在输入静止且持有外部独占锁时使用。

## 3. 筛选与训练

按[数据与训练](references/training.md)先排除其他说话人、错误语言、BGM/混响过重、重复、失真和无有效语音的片段；保留原件、来源时间区间和排除理由。先按原始录音/台词/重复组留出，再切片；重叠窗口不能跨 train/holdout，holdout 不得进入检索索引。历史中文运行没有独立验证集，不得倒填。

逐阶段执行预处理、F0、HuBERT。`per=3.7` 是分块秒数，静音阈值为 -42 dB；v2 特征 768 维。`build_filelist.py` 默认拒绝不齐全样本，审查缺失列表后才用 `--allow-incomplete`，在报告中分列真实交集和 2 条 mute；进一步在 RVC 环境验证数组/音频内容。

训练前确认输出目录和配对底模，保存 CLI 与配置的差异；定期核对 G/D 和小模型确实保存。e50/e100/e150/e200 等候选用同一留出片段和演唱短段比较，不能默认 e150 最佳或仅以 loss 排序。小模型用于推理，G/D 用于恢复；只能载入可信档案。

## 4. 索引和转换关口

冻结特征集并验证 added 索引的新鲜度；上游会跳过已存在 added，也可能复用旧 trained，故变更特征时用新索引实验目录。训练四路交集和索引特征集合分别记录，历史是 86 vs 87，不得混为同一个计数。

按[推理混音](references/processing.md)复用 DDSP 模板的分离方法，但不要执行其 DDSP 推理命令或加载 DDSP 权重。先审听分轨并冻结主唱/和声映射，再用配对 RVC 小模型/added 索引做短段 API 调用。显式设置环境根，不用 `setdefault` 或全局缓存串角色；每个声部新进程。检查返回采样率、非空有限值和 PCM 缩放，保留干声。

## 5. 验收、恢复和交付

听审短段后才整曲转换；模型、索引率、protect、移调每次只改一个变量。对齐时核对伴奏 frames、起点与内部漂移，不用强制拉伸掩盖错误；混音只复用哈希一致且已审听的声部。保留 raw、dry、FX、premaster、master 和人工工程，不能删干声或覆盖用户手动混音。

按[恢复表](references/repair.md)只重跑受影响阶段；未知进程状态先查进程/日志/产物，不重复训练。完成须有实际交付文件、解码与格式/时长/响度/真峰值检查、谱系与明确听审结果。未听审只能交付 `awaiting-listening-review` 候选。分别报告历史证据、离线检查与本次真实训练/推理，不能互相替代。

需要画面时可选[律动环 MV](../../music-visualizer/rhythm-ring/README.md)，只移交已冻结母带及哈希；不自动发布任何音频或模型。
