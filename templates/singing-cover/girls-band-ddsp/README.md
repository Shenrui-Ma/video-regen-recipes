# 少女乐队 DDSP-SVC 翻唱

将已有演唱转换为少女乐队角色音色，保留原唱的旋律、发音、节奏与表现，再与伴奏和独立和声混音。不是文本生歌、零样本克隆，也不是 H3 剧情生成。

**状态：历史资料已整理，公开版标准库预检与离线测试已验证；此次未部署 Linux 环境、未加载模型、未运行 GPU 推理、未审听歌曲。** 注册八个角色不代表八个角色全部做过歌曲。详见[验证边界](references/validation.md)。

## 关联成品

| 成品 | 角色 | 阅读重点 |
| --- | --- | --- |
| [𝑺𝑻𝑨𝑹𝑩𝑶𝒀 高松灯](https://www.bilibili.com/video/BV1BPgq6hEey/) | 高松灯 / `tomori-30000` | 原调重推、和声阈值、四尾音修复与手动混音版本分离 |
| [𝑩𝒊𝒍𝒍𝒊𝒆 𝑱𝒆𝒂𝒏 —— 千早爱音](https://www.bilibili.com/video/BV1dQKY6ME3t/) | 千早爱音 / `anon-12000` | 声部分配、错误音节诊断与窄范围返修 |

两条链接由本仓库作者提供；历史版本与公开视频的关联边界见[来源说明](sources.md)。

## 准备什么

- 有权使用的原曲录音，或已审听并有哈希的伴奏、主唱、和声。分轨应同起点、同采样率，保留未处理版本；不附带第三方歌曲、歌词和模型权重。
- 从[角色清单](model-catalog/voices.json)选一个 checkpoint 和配对 config；同时准备 ContentVec legacy 500、RMVPE 230917、PC-NSF-HiFiGAN **2025.02**。从整曲开始还需要三个分离模型。
- 独立 **Linux NVIDIA GPU** 推理环境；本机 macOS/Linux 负责输入、计划、传输、状态与取回核验。本模板不声称 MPS 适配，不固定服务器地址、GPU 编号或最低显存。
- FFmpeg/ffprobe 和人工审听条件。模板自带预检仅需 Python 3.10+ 标准库；外部推理工具的依赖需另行安装。

**感谢角色模型作者路边墨缇斯**，分享来源为 [BV1JU2LBZEt5](https://www.bilibili.com/video/BV1JU2LBZEt5/)。资料中的教程上传者未知，不将其自动等同于模型作者或上述成品 UP 主。DDSP-SVC 代码作者为 yxlllc；依赖、声码器、角色模型和歌曲权利各自独立，见[来源与许可](sources.md)。

## 工作路线

1. 确认歌曲、角色、用途与授权；新建项目 ID，保存输入 SHA-256、真实格式与父版本。
2. 按[部署说明](references/deployment.md)固定 pymss **2.0.14 / core 0.1.4** 和 **DDSP-SVC 6.2 + PC vocoder 2025.02**，先校验模型字节，再做短段环境测试。
3. HyperACE v2 分总人声/伴奏，Gabox karaoke 分两候选，分别尝试 dereverb。保留 raw/noreverb/reverb，以歌词覆盖和审听决定 lead/backing，不凭文件名或 LUFS 排序。
4. 冻结声部映射后，原调 `key=0` 起步，分别转换主唱、和声；短段先检查字词、F0、音色、高音、呼吸，再做整曲。
5. 按伴奏 frame count 对齐，按原人声总线关系重算混音增益，制作 premaster 和两遍响度处理母带。
6. 按[处理与验收](references/processing.md)完整解码、复测真峰值、听审；坏字只重做受影响声部/区间，见[局部修复](references/repair.md)。

可改歌曲、八角色之一、移调、两声部角色、去混响选择、局部参数、混音和节选。不要以改文件名方式混入 DDSP 6.3、RVC 或其他 vocoder；新角色也需独立配对及短段验收。

## 最小离线入口

在仓库根目录执行。计划只列材料和关口，不发出 GPU 作业：

```bash
python3 templates/singing-cover/girls-band-ddsp/scripts/preflight.py --voice tomori-30000
python3 -B -m unittest discover -s templates/singing-cover/girls-band-ddsp/tests -v
```

准备好自己模型库后，将 `MODEL_ROOT` 设置为其绝对路径。文件布局见部署说明。检查会读取所选角色、四份共享文件及六份分离文件；没有附权重，因此空目录检查失败是正常结果。

```bash
python3 templates/singing-cover/girls-band-ddsp/scripts/preflight.py --voice tomori-30000 --check --model-root "$MODEL_ROOT"
```

仅复用已验收干声时可加 `--ddsp-only`，它只省略分离模型校验，不证明输入已经验收。脚本不下载、不执行 shell、不反序列化 checkpoint；成功只表示受检文件字节匹配，不表示授权、CUDA、模型加载或听感通过。

## 交付与下一步

交付 `master.wav`、`premaster.wav`、已对齐的伴奏/转换主唱/转换和声、实际参数与声部映射、父版本及输入输出 SHA-256、独立 QC 和人工审听记录。不将仅生成计划标为完成，不擅自投稿。

音频交付即完成本模板。需要字幕和画面时，将**已冻结母带及哈希**交给独立的[律动环 MV 模板](../../music-visualizer/rhythm-ring/README.md)；可复制其 `examples/project.json` 到自己的项目，绑定 `audio` 与 `audio_sha256`，再配置 `image`、`font`、`output`、`start/duration` 节选与输出相对时间的 `cues`。MV 使用独立 `scripts/render.py`、Python/Pillow/FFmpeg，不需要 SVC 环境。两个环为全频/180 Hz 低通立体声 RMS 包络，不是 FFT 频谱或节拍检测；该 MV 是独立实现，不宣称原片逐像素重现。无需等 MV 才算翻唱完成，MV 不反向成为 DDSP 输入。

Agent 从 [SKILL.md](SKILL.md) 开始；机器索引见 [profile.json](profile.json)。

配方：**Shenrui Ma（四倍体果蝇）**。角色模型、代码与依赖作者分别见上方致谢及来源页。
