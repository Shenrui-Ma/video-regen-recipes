# 指定角色 RVC 训练与翻唱

为你指定的角色整理有权使用的语音、训练 RVC 音色，再将已有歌曲的演唱转换为该音色，保留旋律、节奏与发音，经分声部试听和混音交付音频。不是文本生歌、零样本克隆，也不要求先有 DDSP 模型。

**状态：历史资料已整理；本模板 helper 的离线测试已验证。此次没有训练、下载语音或模型、连接 SSH、GPU 推理或歌曲听审；新角色和新环境仍需逐阶段验收。**

## 准备什么

- 角色、作品、目标语言，可选配音演员。Agent 先按[来源发现](references/discovery.md)查官方/可信角色资料与语音，再用 yt-dlp 元数据搜索兜底；不要一开始就要求用户找齐素材。找不到可用来源后才请求用户补充。
- 有权使用的角色录音和待翻唱歌曲，或同起点的已审听主唱、和声、伴奏。角色身份、语言、CV、录音/表演/角色/歌曲权利分别核验，公开可访问不等于可训练或可发布。
- 独立 Linux NVIDIA GPU 环境、Python 3.12、FFmpeg/ffprobe；固定 RVC v2/48k/F0 路线及匹配底模、HF 格式 HuBERT、RMVPE、mute 资产。控制和传输与训练分开，不固定主机、设备号或显存承诺。
- 人工筛选、分组留出及代表段听审。几分钟对白可用于原型探索，不保证能覆盖歌唱高音、长音与弱音。

## 保姆级路线

| 阶段 | 要做什么 | 通过后保留 |
| --- | --- | --- |
| 01 来源 | 搜索、逐项核对角色/语言/CV、确认使用范围 | 候选元数据、来源判断与本次权利记录 |
| 02 部署 | 固定源码、隔离环境、校验配对资产、短段加载测试 | commit、环境清单、依赖 SHA-256 |
| 03 数据 | 保留原录音，筛选/去重，按原始录音或台词组留出 | 清单、源区间、train/holdout 分组与哈希 |
| 04 特征 | 预处理、F0、768 维特征、四路交集 filelist | 日志、排除原因、角色样本和 2 条 mute 分列 |
| 05 训练 | 分阶段保存，固定测试片段比较 checkpoint | G/D 恢复档、小模型、实际参数与选择理由 |
| 06 索引 | 对冻结特征建 added 索引，校验是否过期 | 特征成员/哈希、维度/ntotal、索引哈希 |
| 07 翻唱 | 分离与听审、短段 RVC，再独立转换声部 | 源分轨、转换干声、实参和哈希 |
| 08 交付 | 对齐、混音、独立 QC、全曲听审、恢复记录 | dry、FX、premaster、master 与版本谱系 |

依次阅读[部署](references/deployment.md)、[数据与训练](references/training.md)、[推理混音](references/processing.md)、[恢复与哈希护栏](references/repair.md)、[验证边界](references/validation.md)。Agent 从 [SKILL.md](SKILL.md) 开始；机器索引见 [profile.json](profile.json)。

## 离线入口

在仓库根目录执行，不下载或启动任何训练作业：

```bash
python3 -B -m unittest discover -s templates/singing-cover/character-rvc/tests -p 'test_helpers.py' -v
python3 templates/singing-cover/character-rvc/scripts/build_filelist.py --help
python3 templates/singing-cover/character-rvc/scripts/run_guard.py --help
```

helper 只需 Python 3.10+ 标准库。`build_filelist.py` 检查实际文件并构建 v2/48k/F0 单说话人列表，不解码 WAV 或加载 NPY；`run_guard.py` 校验文件字节、目录成员和显式参数，不代替进程锁、模型可信性、授权或听审。真实调用与失败恢复见对应参考页。

## 历史示例，不是默认角色

莫斯提马（Mostima，明日方舟）中文配音若舞：历史材料记录一条 246.677333 秒的合集，预处理 87 段，最终四路训练交集 86 段、194.20 秒，另有 2 条 mute；索引用全部 87 份 HuBERT 特征。e150 是当时脚本选用，不是独立验证集选出的最佳模型。

[BV17a411d7ex](https://www.bilibili.com/video/BV17a411d7ex/) 是转载/整理语音入口，**不是官方账号或本次 RVC 翻唱成品**。本模板不附权重、索引、录音、ASR 全文，不用其他角色成品冒充本次成果。历史训练和成品证据的限制见[来源与致谢](sources.md)。

交付音频即完成本模板；需要画面时可另接[律动环 MV](../../music-visualizer/rhythm-ring/README.md)，只传递冻结母带与哈希，MV 不成为训练前置条件。

配方：**Shenrui Ma（四倍体果蝇）**。感谢 **RVCProject / RVC-Project**、原角色中文配音**若舞**与明日方舟游戏权利主体；技术代码、角色、录音、表演和歌曲权利分别归各自权利人。

## 配套资源

- [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)：本仓库其它模板使用的固定版本工作流；本模板是音频链路，不调用它做推理
- [Shenrui-Ma/video-regen-assets](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets)：公开素材库；本模板不附带权重、索引或录音
- 配套入口：[语音发现脚本](scripts/discover.py) · [依赖与哈希](model-catalog/dependencies.json) · [律动环 MV](../../music-visualizer/rhythm-ring/README.md)

第三方代码、权重、角色与声音权利见 [LICENSES.md](LICENSES.md)，本次验证范围与权利登记要求见 [验证记录](references/validation.md)。
