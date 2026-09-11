# 来源、致谢与公开范围

本模板根据本仓库作者提供的《少女乐队 SVC 翻唱保姆级溯源资料包 v1.0》（2026-09-12）重新提炼，未复制私有 runner、整包证据、权重或媒体。来源名用于追溯，不要求公开读者持有私有包；关键模型哈希与方法已在本目录独立列出。

原作与配方：**Shenrui Ma（四倍体果蝇）**。此署名与第三方角色模型/代码作者署名各自独立。

## 角色模型与案例

**明确感谢角色模型作者路边墨缇斯。** 原分享/教程来源：[BV1JU2LBZEt5](https://www.bilibili.com/video/BV1JU2LBZEt5/)。作者身份及非商业使用说明来自资料包保存的搜索索引摘录；当时 Bilibili API 返回 412，上传者未知。因此不把模型作者自动等同于教程上传者，也不推断成品 UP 主身份。

资料记录作者允许合规非商业使用、可不署名，但本模板仍保留致谢。该摘要不是完整授权文本，也不覆盖原曲、录音、声优或角色 IP；新用户应自行核实原声明、使用范围与发布权利。没有随模板传递任何私人授权确认。

本仓库作者提供的两条关联成品：

- [𝑺𝑻𝑨𝑹𝑩𝑶𝒀 高松灯](https://www.bilibili.com/video/BV1BPgq6hEey/)
- [𝑩𝒊𝒍𝒍𝒊𝒆 𝑱𝒆𝒂𝒏 —— 千早爱音](https://www.bilibili.com/video/BV1dQKY6ME3t/)

本次整理尝试抓取两条成品页及原教程页，均被平台拒绝，未能独立验证。名称按作者提供文本保留；公开链接不证明某个历史修订就是上传版，也不证明全部候选已验收或公开视频音轨与某份母带逐字节相同。

## 代码与共享依赖

| 组件 | 作者 / 固定来源 | 资料中的许可边界 |
| --- | --- | --- |
| DDSP-SVC 6.2 | [yxlllc / aeaba53f](https://github.com/yxlllc/DDSP-SVC/commit/aeaba53f46fbb4e8177af444c5c56660f55b1787) | 代码 MIT，不覆盖全部权重 |
| pymss 2.0.14 | [pymss-project / dfe1def1](https://github.com/pymss-project/pymss/tree/dfe1def1ee9b880b5380b83e5e5b920eed631774) | 代码 MIT；core 0.1.4 与环境其余依赖逐项保留许可 |
| ContentVec legacy 500 | [auspicious3000 / ContentVec](https://github.com/auspicious3000/contentvec) | 代码 MIT，Box 权重独立 notice 未齐全；500 不是训练步数 |
| RMVPE 230917 | [yxlllc 发行](https://github.com/yxlllc/RMVPE/releases/tag/230917)；原论文实现 Dream-High | 所用权重许可不清楚，不能套用 RVC 或另一个实现的许可 |
| PC-NSF-HiFiGAN 2025.02 | [OpenVPI / DiffSinger Community Vocoder Project](https://github.com/openvpi/vocoders/releases/tag/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02) | 资料保存的发行声明为预训练权重 CC BY-NC-SA 4.0；使用/再分发前阅读原包 notice |
| HyperACE v2 | [pcunwa / unwa](https://huggingface.co/pcunwa/BS-Roformer-HyperACE) | 原权重许可未厘清 |
| Gabox karaoke / Lead_VocalDereverb | [GaboxR67](https://huggingface.co/GaboxR67/MelBandRoformers) | 原权重许可未厘清 |

分离配对配置引用 [pymss 部署镜像](https://huggingface.co/baicai1145/pymss/tree/f02318ef92c43472777ed7aeeded3d2b29a68b58)。镜像卡的 Apache-2.0 不自动证明原作者授予再许可；pymss 的 MIT 也不覆盖它们。哈希及固定下载入口见 [dependencies.json](model-catalog/dependencies.json)。

角色免署名声明不抵消声码器署名、非商业及适用范围内相同方式共享的要求。对于生成音频，不能仅凭模型许可证摘要就断言所有输出都必须或都不必套用同一许可证；发布前检查具体条款与素材权利。未知许可不等于允许使用或商用。本仓库 MIT 不重新许可任何第三方权重、配置或歌曲。

## 证据提炼边界

依据资料包 `models/models.md`、`models/models.json`、八份角色 manifest、部署定义、`main_reflow.py` 参数解析快照、操作手册、谱系和后期报告。后补的 `verification/remote-model-hashes.json` 优先解释早期模型审计的时间差，不能把早期“未读远端”与后期“字节匹配”写成矛盾或新推理。

本公开版只保留来源、兼容组合、期望字节及方法总结；不带私人绝对路径、主机/账号、网盘提取信息、凭据、原包授权布尔值、完整日志、SESX、第三方脚本或权重。公开来源 URL 不保证当前下载可用，不构成授权担保。发布歌曲应清晰披露 AI 音色转换与任何原唱局部保留，避免暗示官方作品或原声优亲唱。
