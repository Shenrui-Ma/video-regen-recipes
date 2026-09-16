---
name: girls-band-ddsp-cover
description: 从已有歌曲或已审听分轨制作少女乐队 DDSP-SVC 6.2 翻唱；本机控制、独立 Linux GPU 推理，经过模型配对校验、分离听审、分声部转换、局部修复与混音，交付母带分轨和哈希，不依赖 MV。
version: 0.1.0
author: Shenrui Ma（四倍体果蝇）
license: "See LICENSES.md for component terms"
platforms: [linux]
---

# 少女乐队 DDSP-SVC 翻唱

## 1. 明确输入与权限

读取 [README](README.md)、[sources](sources.md) 和 [profile](profile.json)。用户指定优先；未给歌曲/角色时只补齐缺少项，不自动下载热门歌或替换角色。创建新 job ID 和新输出目录，不覆盖历史工程。记录 `source_sha256`、角色 ID、原调或移调、主唱/和声选择、用途与待审授权。不能继承旧资料中的授权确认。

默认保持原调，主唱和和声同角色，44.1 kHz PCM24 音频交付；和声缺失或不可用时明确记录，不用重复主唱伪造和声。两角色需求分别校验模型、执行和验收。

## 2. 固定运行环境与材料

按[部署说明](references/deployment.md)操作。本机负责控制和传输，Linux GPU 负责分离/DDSP；不声称本机 MPS 可用。读取 `model-catalog/voices.json` 和 `model-catalog/dependencies.json`，运行 `scripts/preflight.py`。默认只是非执行计划；`--check` 才读取文件哈希。它不是任务提交器，也不检查 GPU/授权。

获得匹配源码、隔离依赖和权重后，先做可信短段推理。缺源码或权重则列阻断项，不用假文件冒充通过。运行时 GPU 由当前环境调度，保留锁/队列/退出记录；连接中断先查原进程和阶段产物，不能重复提交未知状态作业。

## 3. 分离并停下来审听

按[处理说明](references/processing.md)完成 HyperACE → Gabox → dereverb 候选链。保留原总人声和所有候选，用歌词覆盖、F0、活动比例和人工听审确认声部，输出 `stem_semantics.json`。去混响造成缺字则旁路；不得为了走完流程牺牲内容。

声部映射与审听未确认，状态停在 `awaiting-stem-review`，不批量转换整曲。语义 JSON/YAML 是记录，不是可交给 `main_reflow.py` 的命令。

## 4. 转换与混音

原调起步，使用配对模型和实参日志；主唱 `-60 dB`、和声 `-80 dB` 仅为短段起点。阈值不是音量、移调不是音色、训练 step 不是推理 steps。先审听代表段（含辅音、高音、弱音、和声重叠），不通过则单变量排查，不盲跑整曲。

通过后各声部独立转换，以伴奏样本数对齐，记录裁尾/补零；重算混音增益，保留 dry、FX、premaster、master。两遍响度处理后独立复测，不把样本峰值当真峰值。混音不负责修正已经唱错的音节。

## 5. 局部修复、恢复与交付

按[修复说明](references/repair.md)记录父 stem 哈希、半开样本区间、处理参数与新输出；先干声后短混音试听。原唱局部替换需本次明确接受并披露，不能由旧记录代授权。用户手动保存的工程优先，不重跑旧混音覆盖它。

分离通过而转换失败只重跑对应转换；仅混音失败则复用哈希一致分轨；QC 环境失败先修 QC，不重新推理。哈希变更的输入会使所有相关下游结果失效。

完成条件是本次母带/分轨实际存在，完整解码、格式/时长/响度与真峰值检查完成，听审结论明确，输入输出哈希和谱系齐全。缺听审时交付候选并标 `awaiting-listening-review`，不得写最终接受。历史资料、离线脚本测试与本次 GPU 验证分别报告。

需要画面时可选[独立 MV](../../music-visualizer/rhythm-ring/README.md)，只移交冻结母带，不让画面制作阻塞音频交付。
