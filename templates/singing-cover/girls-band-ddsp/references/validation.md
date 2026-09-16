# 验证状态与证据边界

整理日期：2026-09-12。`adapted-template-offline-checked` 只覆盖公开文档/清单和标准库工具，不是新歌曲通过 GPU 推理的声明。

## 三个层次分开

| 层次 | 可以确认 | 不能推导 |
| --- | --- | --- |
| 历史制作资料 | 分离、转换、混音、局部修复与多版本记录，角色/输入/输出关联 | 所有候选均获用户接受，或八角色全都实测 |
| 资料包当时的复核 | 报告记载14模型/26份权重及配对配置远端 SHA 全匹配，四份运行 lock 匹配；130项旧代码测试通过 | 本模板本次连接远端或执行了130项测试，完整源码等于历史 commit |
| 本次公开版检查 | JSON/配对哈希提炼、入口参数静态核对、标准库预检的离线正反例 | GPU可用、权重加载成功、MPS适配、整曲音质或许可已验收 |

资料早期模型分项审计“未访问远端”与后来“远端字节实算匹配”发生在不同时间；以最终补充解释状态，不能删掉本地坏副本事实。哈希匹配只证明字节身份，不证明质量、权利或安全反序列化。

## 历史案例，不充当本次成品

| 案例/日期 | 输入与结果证据 | 实际时长/耗时与限制 |
| --- | --- | --- |
| Starboy / 2026-07-20 至24 | 高松灯初始+12、原调重推、和声-85、四尾音及手改工程是不同版本 | 某手改音频节选81.5秒，3594150 frames；另有81秒视频。完整工程规范10294784 frames。不得混成同一导出；新推理耗时未测 |
| Billie Jean / 2026-07-20 至后期修复 | 千早爱音；声部重映射与01:17两个窄音节修复 | 资料现存PCM24母带293.568005秒、12946349 frames；逐版本接受与导出后mask外相等未闭合；新推理耗时未测 |
| 让风告诉你 / 2026-07-21制作，09-12资料复核 | AAC源实际48k双声道；高松灯原调、主唱去混响/和声raw；资料复核完整PCM24母带解码和历史SHA一致 | 资料独立重测-14.00 LUFS-I、-1.20 dBTP，仅该文件有效，不外推给两条关联成品 |

特别是 Starboy 81秒视频与81.5秒 WAV 不应说成逐样本同一音轨；Billie Jean 原唱局部替换授权原话与最终听感接受在公开提炼证据中未闭合。

历史部署为 Linux NVIDIA CUDA 路线；资料没有提供足以公开断言最低显存、各模型峰值显存、全曲统一速度的记录。本次未运行GPU，不报告虚构的推理耗时。更换硬件、源码、依赖、角色、曲目都需要重新测试。

## 本次可重复离线验证

从仓库根目录运行：

```bash
python3 -B -m unittest discover -s templates/singing-cover/girls-band-ddsp/tests -v
python3 -B templates/singing-cover/girls-band-ddsp/scripts/preflight.py --voice tomori-30000
```

2026-09-12 在本机 Python 3.13.13 执行17项测试全部通过。测试使用临时小字节文件模拟匹配与损坏，不构造伪权重冒充部署成功。覆盖八角色清单、角色/共享/分离文件计数、未知角色拒绝、大小与 SHA 不一致、缺文件、目录、非法路径、symlink 越界、合法库内链接及 CLI 退出码。另与只读资料包逐项核对26份文件的期望哈希一致；这是转录核验，不是新权重实测。

预检成功标 `byte-integrity-checked`；计划标 `plan-only`。两者均显式 `gpu_inference: not-run`、`listening_review: pending`，不能把退出码0解释为模型已能运行。工具不验证 CUDA/torch 安装、音频内容、路径在运行源码中的绑定或权重许可，也不执行下载、SSH、GPU、音频解码、pickle/YAML 加载。

## 新环境验收台账

实际复现时在自己的项目记录日期、操作系统/GPU/驱动、源码commit与diff、实际依赖lock、模型及source hash、argv、起止时间/耗时、输出格式/frames、分离审听、F0和字词检查、独立LUFS/dBTP、修复/拒绝版本、最终接受状态。技术检查和人工听审各自填真实状态，不预填成功。

本模板未附模型、原曲、完整分轨、旧部署lock、私有runner、旧字幕cue或完整DAW工程，因此不是全离线复现包。独立MV另行验收，本模板完成条件仅为经验证的母带/分轨/哈希。

## 契约状态

- `runtime.distribution_mode = repo-bound`，`runtime.entry = scripts/preflight.py`，`runtime.environment_lock = model-catalog/dependencies.json`。
- `runtime.existing_environment_verified = true` 只表示历史成品在作者的独立 Linux GPU 环境完成；`runtime.clean_install_inference_verified = false`。
- 声码器 PC-NSF-HiFiGAN 2025.02 的发行声明为 **CC BY-NC-SA 4.0（非商业）**；其余权重许可有未厘清项，逐项见 [LICENSES.md](../LICENSES.md)。
