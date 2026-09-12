# 推理 API、混音与交付

输入必须属于本次已确认用途的材料，模型/added 索引已完成配对和[新鲜度检查](training.md)。本页是固定源码接口操作说明，片段未在此次加载模型执行，不是一键总控。

## 1. 分离、声部与短段

只有混音原曲时，复用 [DDSP 模板的处理页第 1–2 节](../../girls-band-ddsp/references/processing.md)：pymss 2.0.14/core 0.1.4，HyperACE v2 分总人声/伴奏，Gabox karaoke 分两候选，可分别尝试 Lead_VocalDereverb。模型来源与权利独立核验，保留 raw/noreverb/reverb 三种结果及 hash。

**仅复用分离方法，不运行其 DDSP 推理步骤，不需要 DDSP 权重、角色 config、ContentVec legacy `.pt` 或 PC vocoder。** 已有可信、已审听分轨可跳过分离并保留来源哈希。

人工决定主唱/和声与去混响版本，以歌词覆盖、主旋律连续性、活动/F0 及听感判断，不能以文件后缀、最高 LUFS 或最“干净”判断。去混响吞字就旁路。没有和声时记录缺失，不复制主唱伪造。冻结 `stem_semantics.json`：源分轨 ID/hash、角色、版本、是否去混响、审听状态和理由。

先选 10–20 秒代表段，至少覆盖辅音、弱音、长音、高音及重叠处。主唱和和声分开推理；多角色时每轨用独立模型/索引清单、进程和输出，避免显存对象或环境变量串角色。

## 2. 固定版 Python API

官方 [`infer/vc/modules.py`](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/4338f12c3c28c80b3ac015e2d0df66c41592746d/infer/vc/modules.py) 的签名为：

```python
vc.get_vc(model.name)
status, result = vc.vc_single(
    0, str(input_audio), key, "rmvpe", str(added_index),
    index_rate, 0, rms_mix_rate, protect,
)
```

九个位置参数依次是 `sid, input_audio_path, f0_up_key, f0_method, file_index, index_rate, resample_sr, rms_mix_rate, protect`。第七个 **0 是 resample_sr**，不是旧接口的 filter_radius。返回 `status, (sr, audio)`，异常可能是 `(None, None)`；仅见到 status 字符串不代表成功。

`Config()` 会再次解析 argv；自建入口必须先 argparse 保存自己的参数，再在导入 Config 前设置 `sys.argv=[sys.argv[0]]`。明确在固定 RVC 根设置 import 路径/cwd；不要把下面片段直接丢进已有多模型长驻进程。上游 `get_vc` 根据 `weight_root + model.name` 读取 checkpoint，所以绝对模型参数本身不能防止遗留环境串模型。

以下**单次进程示例**读取由操作者显式绑定的 `RVC_APP, MODEL, ADDED_INDEX, INPUT_AUDIO, NEW_OUTPUT` 环境变量（全部为绝对路径）。模型/索引必须预先通过信任、哈希、角色和版本核验，输出父目录已创建。它不下载、不寻找“最新模型”，不存在的输出用独占创建保护。

```python
import os
from pathlib import Path
import sys

app = Path(os.environ["RVC_APP"]).resolve(strict=True)
model = Path(os.environ["MODEL"]).resolve(strict=True)
index = Path(os.environ["ADDED_INDEX"]).resolve(strict=True)
source = Path(os.environ["INPUT_AUDIO"]).resolve(strict=True)
output = Path(os.environ["NEW_OUTPUT"])
if not output.is_absolute() or output.exists():
    raise ValueError("Use a new absolute output path")
if not all(p.is_file() for p in (model, index, source)):
    raise ValueError("Model, index and input must be files")
if not index.name.startswith("added_") or "trained" in str(index):
    raise ValueError("Bind the real added index; upstream rewrites 'trained' paths")

# Explicit assignments are required before RVC imports, never setdefault.
os.environ["weight_root"] = str(model.parent)
os.environ["index_root"] = str(index.parent)
os.environ["outside_index_root"] = str(index.parent)
os.environ["rmvpe_root"] = str(app / "assets/rmvpe")
os.chdir(app)
sys.path.insert(0, str(app))
sys.argv = [sys.argv[0]]

import faiss
import numpy as np
import soundfile as sf
from configs.config import Config
from infer.vc.modules import VC

idx = faiss.read_index(str(index))  # Only a previously trusted index.
if idx.d != 768 or not idx.is_trained or idx.ntotal <= 0:
    raise ValueError("Invalid v2 added index")
del idx
vc = VC(Config())
vc.get_vc(model.name)  # Only a previously trusted checkpoint.
if (vc.version, vc.if_f0, vc.tgt_sr) != ("v2", 1, 48000):
    raise ValueError("Wrong model profile")
status, result = vc.vc_single(
    0, str(source), 0, "rmvpe", str(index), 0.65, 0, 1.0, 0.33
)
if result is None or result[0] != 48000 or result[1] is None:
    raise RuntimeError(status)
sr, raw = result
raw = np.asarray(raw)
if raw.ndim != 1 or raw.size == 0 or not np.isfinite(raw).all():
    raise ValueError("Empty, non-mono or non-finite inference output")
if np.issubdtype(raw.dtype, np.signedinteger):
    limits = np.iinfo(raw.dtype)
    audio = raw.astype(np.float64) / float(max(abs(limits.min), limits.max))
elif np.issubdtype(raw.dtype, np.floating):
    audio = raw.astype(np.float64)
else:
    raise ValueError("Unrecognized PCM representation")
if not np.isfinite(audio).all() or np.abs(audio).max() > 1.0:
    raise ValueError("Ambiguous or out-of-range float PCM; inspect the return contract")
with output.open("xb") as stream:
    sf.write(stream, audio, sr, format="WAV", subtype="PCM_24")
print(status)
print({"sample_rate": sr, "frames": len(audio), "peak": float(np.abs(audio).max())})
```

把实参、状态、输入/模型/索引 SHA、耗时、输出 hash 和日志保存在私有 job。上面 `ntotal>0` 只检查非空；还须与对应 index receipt 的向量数一致，不能因此认定索引来源匹配。调用成功后检查实际路径状态和短段听感；上游可能对索引读取异常做回退，需审查日志确认检索实际使用，不只相信成功状态。

### PCM 缩放为什么必须做

固定 `infer/vc/pipeline.py` 末尾把归一化波形乘 32768 后转 `int16`，因此返回 `int16` 时先转 float 再除 **32768**，不能把整数值直接当 `[-1,1]` 浮点交给 SoundFile，否则会严重削波。不能对 int16 原地取绝对值估计满量程，最负数有溢出风险；示例使用 dtype 的理论范围。

历史 wrapper 对“浮点但 peak>2”的数据自动除 32768，是兼容启发式，可能把真实异常误判为 PCM16。新入口默认**拒绝模糊幅度**；只有确认调用路径真的返回 float-PCM16，且原始值有限、范围在 `[-32768,32767]`，才在独立、明确标记的适配分支除 32768 并记录表示类型，不通过峰值猜测自动触发。标准 float 输出保持原电平，不再重复缩放。技术输出需另测削波比例、活动比例和听感，finite/peak 检查不等于声音正常。

## 3. 调参、短段听审与整曲

历史中文主唱/对白：key=0、index_rate=0.65、rms_mix_rate=1.0、protect=0.33；和声 index_rate=0.55。这些只是历史起点，**不是新角色最优配置**。

- `key=0` 先保持原调，不因男声转女声固定 +12；移调会改旋律音高，不是音色强度。
- index_rate 在 0..1 内比较，0 可作无检索对照；较高检索可能增强目标纹理，也可能损伤发音，需同段 A/B。
- rms_mix_rate 在 0..1 内调包络融合，不是最终混音 gain。
- protect 常用 0..0.5，0.5 表示关闭此保护；辅音/呼吸变化用短段听审判断，不承诺“更小永远更好”。
- speaker 固定 0；RMVPE 与 resample_sr=0 保持模型 48k 输出，不代表交付母带也必须 48k。

每次只改一个变量，比较同一片段和近似响度下的音色/字词/F0/高弱音。干声出现错字、掉句、噪声或异常音高，先排模型语言、声部分离、F0、输入和索引；不要靠混响掩盖。没通过短段不批量整曲，未听审状态为 `awaiting-listening-review`。

## 4. 对齐、混音和母带

保留 `source-stems`、`converted-dry`、`aligned`、`fx`、`premaster`、`master` 独立版本。RVC 输出 48k，交付可采用 44.1k 双声道 PCM24；重采样只在明确的对齐/混音阶段一次执行，保留原 48k 干声。

以伴奏**真实 frame count 与起点**为时间基准：先查头部偏移、中段同步和尾部长度，再记录每轨补零/裁尾样本数。轻微块尾误差可补零/裁尾，大幅不符或内部漂移必须排查，不能整轨拉伸掩盖。单声道转双声道只是路由，不宣称获得立体声信息；FX 尾声先审听再裁到目标长度。

初始混音可以只有增益与必要 EQ，随后再加轻量空间效果。测原总人声/伴奏关系、FX 后主唱与和声响度及人声总线，按本曲重算 gain；不用旧中文或日文工程的增益硬套。FFmpeg aecho 是延迟效果，不等同专业混响。保留滤镜/插件配置和用户手动工程，不自动以脚本混音覆盖。

推荐将 -14 LUFS-I / -1.2 dBTP 作为可调整预览目标，非全平台规定。premaster 先无削波、无异常空段，再两遍 loudnorm：第一遍分析**同一 premaster**，将 input_i/input_tp/input_lra/input_thresh/target_offset 对应填入第二遍 measured_I/measured_TP/measured_LRA/measured_thresh/offset；目标 I/TP/LRA 一致，显式输出采样率/通道/PCM24，保留实际 linear/dynamic 模式。缺任一测量值停止，不能编造或复用另一版的分析值。

两遍渲染后独立测最终文件，读取下面分析结果的 **input_i/input_tp**，不是输出侧预测值。样本峰值不是真峰值；过冲则在新版本降低目标/保留余量后重算并复测。

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels,bits_per_raw_sample -of json "$FINAL"
ffmpeg -v error -i "$FINAL" -f null -
ffmpeg -hide_banner -nostats -i "$FINAL" -af loudnorm=I=-14:TP=-1.2:LRA=11:print_format=json -f null -
ffmpeg -hide_banner -i "$FINAL" -af silencedetect=noise=-55dB:d=2 -f null -
```

同时记录完整解码后的 frames、有限值/样本峰值、响度、真峰值、编码和时长；静音检测是疑点提示，不能自动判定歌曲有意静音为失败。全曲听审检查字词、边界点击、和声冲突、头尾与目标音色。

## 5. 交付

交付本次 master、premaster、原始和对齐版转换干声、伴奏、可用和声、FX、混音参数/工程、输入输出 SHA、模型/索引配对清单、版本谱系及 QC/听审状态。技术通过但没听审只能交付候选；不能擅自投稿或公开训练集、权重和索引。

恢复只重做[受影响阶段](repair.md)。音频通过即可结束；可选[律动环 MV](../../../music-visualizer/rhythm-ring/README.md)另接冻结母带与 SHA，不能拿别的角色视频或旧日配歌曲当本次中文 RVC 成品。
