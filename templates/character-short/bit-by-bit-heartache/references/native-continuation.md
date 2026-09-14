# 原生 AV latent 续接：参数语义与对照检查

> 历史来源记录：本页描述旧实现/回收阶段。新安装使用 [当前生成路径](generation.md)与[环境说明](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/README.md)，不需要旧私有Save/Load/Trim节点。


本页补充 [generation.md](generation.md) 的续接规则，供 Issue #1 的社区复现者核对自己的实现。**这里只公开参数语义与当前回收源文件的 SHA-256，不发布节点实现，不保证其他同名节点行为一致。**“原生”在本页指直接使用前段联合视频／音频 latent 的路线，不表示这些自定义节点是官方内置节点。

证据是当前可读源码的静态检查：来源尚未完整固定，未固定包版本、上游 commit 或历史运行时版本；当前 SHA **不是历史生成 commit 的证明**。未执行这些源码、补丁自测或 GPU 采样。源码中的效果评价不作为本页的实测结论。

## 1. 两套接口必须分开

| 用途 | `HermesH3Continuation` 当前接口 | `h3_motion_context` 当前接口 |
| --- | --- | --- |
| 保存 | `SaveMiniMaxH3AVLatent` | `MiniMaxH3MotionContextSaveLatent` |
| 加载 | `LoadMiniMaxH3AVLatent` | `MiniMaxH3MotionContextLoadLatent` |
| 注入 | `ApplyMiniMaxH3MotionContext` | `MiniMaxH3MotionContext` |
| 解码后裁切 | `TrimMiniMaxH3MotionContext` | `MiniMaxH3MotionContextTrim` |

`generation.md` 的路线组合是左列 canonical Save/Load、右列 `MiniMaxH3MotionContext`、左列定长 Trim。不是选任意一列整套替换。类名相近不代表字段、返回值、裁切量或保存格式一致。

## 2. Canonical Save/Load 规则

证据：`HermesH3Continuation/__init__.py` 的 `_av`、`_pixel_frames`、`SaveMiniMaxH3AVLatent.save`、`LoadMiniMaxH3AVLatent.load`。

| 字段 | 精确语义 |
| --- | --- |
| `samples` | Comfy `LATENT` 字典，`samples["samples"]` 必须为包含恰好两个 tensor 的 `NestedTensor`，顺序 video、audio。不是 MP4，也不是普通单路 latent。 |
| video | 五维 `[B,24,Tv,Hl,Wl]`；`Hl/Wl` 是 latent 空间尺寸。 |
| audio | 四维 `[B,32,2,Ta]`；两路 batch 大小必须相同。 |
| 视频时间 | `P=(1,4,4,4,4)`；`F=sum(P[i mod 5], i=0..Tv-1)`。不是所有视频 token 都代表四帧。 |
| 音频时间 | 必须满足 `Ta=round(F/24*40)`。这里 40 是音频 latent 步／秒，不是音频采样率。 |
| `filename_prefix` | 相对 Comfy 输出目录的保存前缀；默认 `h3_latents/ComfyUI`，生成带计数器的 `.safetensors` 文件。 |
| `visible_frames` | 发布长度，默认 243，至少 1；只写 metadata，不裁 latent。 |
| `trim_frames` | 发布区间起点，默认 0，至少 0；只写 metadata，不裁 latent。 |
| `metadata_json` | 必须是 JSON object；键和值转为字符串。保留字段随后覆盖同名自定义字段。不要把私人运行信息直接写入公开产物。 |

文件恰好保存 `video`、`audio` 两个 tensor，detach、contiguous 后移到 CPU；不强制转换 dtype。metadata 保留字段均为字符串：

- `schema="minimax-h3-av-latent-v1"`
- `visible_frames=V`、`trim_frames=s`
- `context_end_frame=E=s+V`

发布区间为从零开始、右端不含的 `[s,E)`；要求 `s>=0`、`V>=1`、`E<=F`。**保存的是完整 canonical，而不是 `[s,E)` 的切片。**保存返回原 `samples`，另有 UI 文件信息。

Load 输入仅 `latent_path`，必须指向文件；它检查文件 tensor 键集合恰为 `{video,audio}`、上述 shape／AV 时间一致性、schema，以及 `1<=E<=F`。输出依次为 `samples`、排序后的 `metadata_json`、整数 `context_end_frame`。它重新构造 `NestedTensor`，不会把 metadata 塞进 conditioning，也不会裁 tensor。当前 Load 不重新验证 `E=trim_frames+visible_frames`；复现者应自行核对 metadata 的内部一致性。

### 另一套 Save/Load 不是相同 schema

`h3_motion_context/nodes.py` 的 Save 输入是 `latent, filename_prefix, clip_index`，返回路径字符串；metadata 为 `format="h3_motion_context_av_v1"`，没有上述发布区间规则。`clip_index>0` 保存固定槽位且会覆盖；0 使用运行计数器。Load 输入为 `latent_path, clip_index`：文件路径直接选该文件；目录索引 0 选最新文件，重试可能误选本段被拒结果；正索引匹配对应槽位。

该 Load 只要求存在 video/audio 键，不校验 canonical schema，返回 `{"samples": [video,audio]}` 普通列表，设计用途仅为 `context_latent`，不是可直接送解码器的 `NestedTensor`。因此“能读文件”不证明两套格式规则一致。续跑应固定前驱文件及其 SHA，而非只依赖“最新”。

## 3. `MiniMaxH3MotionContext`：物理尾端 → 新段头部

证据：`nodes.py` 的 `MiniMaxH3MotionContext.apply`、`_video_tail_from_latent`、`_step_offsets`、`_audio_tail_from_latent`。

必需输入为 `conditioning, vae, latent, context_length, audio_context_length`；`latent` 是本段目标 latent，前段完整 latent 接可选 `context_latent`。可选像素路线为 `context_frames` 及 `context_audio + audio_vae`。接了 `context_latent` 后，视频和音频都优先从它切取，忽略对应已解码输入；不会退回重编码来掩盖尺寸不匹配。输出只有 `conditioning, trim_frames`，不是目标 latent。

当前常量为 `ENCODE_MODE="video"`、`ANCHOR_MODE="head"`、`AUDIO_MODE="timeline"`、`CROP="disabled"`；不是任意安装都可在 UI 调整的字段。视频窗口提供 5、22、39、56 帧；可用帧不足或离散网格不匹配时存在向下选择逻辑，不能只看请求值，须检查实际返回 trim。

设前段有 `Tv` 个视频 token、物理帧数 `F`，视频窗口 `n=22`：

- `k=7` 个 token 恰好覆盖 22 帧，切片为 `video[:1,:,Tv-k:Tv]`，即只取首个 batch。
- 必须有足够 token，且 `(Tv-k) mod 5=0`，否则拒绝。合法 `17g+5` 帧对应 `5g+2` 个 token，确保这些尾窗口的周期相位相容。
- 源窗口为 **`[F-22,F)`，不是 `[E-22,E)`**。
- 每个 token 拆成一个 cond block，新段像素锚点依次为 **`0,1,5,9,13,17,18`**，覆盖 `[0,22)`；返回 `trim_frames=22`。
- 每块携带 `resolved_frame_index=0` 和真正位置 `motion_context_index=p`；由 layout patch 放到目标时间原点加 `(5/3)*p` 的位置。Ref2VA 的参考块会改变时间原点，不能一律以 text 长度代替目标原点。
- 当前源码保留头部范围以外的已有 keyframe（如 last-frame），丢弃会与头部冲突的已有锚点，并设置目标 `minimax_frame_count`。源与目标空间尺寸、通道数须匹配；这一路不提供多 batch 一致续接保证。

### `published-end` 在这里不生效

`MiniMaxH3MotionContext` 没有 `context_end_frame` 输入，也不读取 canonical metadata。Load 输出该数值，**不等于**下游使用它。按 `generation.md` 的时间账本，以完整前驱作为下一段 context 时：

| 前驱段 | canonical `F` | 发布 `[s,E)` | 下一段原生视频 context |
| --- | ---: | --- | --- |
| 1 | 158 | `[0,158)` | `[136,158)` |
| 2 | 192 | `[22,180)` | `[170,192)` |
| 3 | 175 | `[22,163)` | `[153,175)` |

后两行引用了未发布的物理尾部。不能在不改实现／输入的情况下，声称它锚定发布片段最后一帧；也不能把这些当前源码推导冒称历史执行追踪。

### `audio_context_length=24` 的精确映射

字段单位是 **24fps 下的像素帧时长**，与视频窗口独立；0 表示跟随视频 span，**不是关闭音频**。canonical 路线自动带音频，没有 `continue_audio` 开关。

```text
A = int(audio_context_length)；若 A=0，则 A=span
r_requested = round(A / 24 * 40)
r = min(r_requested, Ta)
audio_slice = audio[:1, ..., Ta-r:Ta]
A=24 → 24/24=1 秒 → round(1*40)=40 个音频 latent 步
```

`round` 是源码的 Python 最近整数规则，不是向上取整；不要照 tooltip 的“widened”理解成 ceil。源音频不足则只取现有长度并告警；空窗口报错。

音频位置还有网格补偿，不可仅写“在第22帧结束”：设 `q=5/3`，`o=Ta-qF`。合法最近整数网格通常有 `o=0,±1/3`；若不满足 `-0.5<o<0.5`，当前源码告警并按 0 处理，而非拒绝。

```text
u = round(q*span + o)             # head 模式的目标音频结束坐标
motion_context_audio_end_frame = u/q
音频时间窗口 = [target_origin + u-r, target_origin + u)
```

音频以 `kind="audio"` reference 追加到 `minimax_refs`，再由 patch 移到上述目标时间线，保留原有 Ref2VA references。24帧音频窗口可以长于22帧视频窗口，不增加视频 trim。它取的是源音频物理尾端，并不从已发布音轨取尾。像素／解码音频路线会重编码尾音频且采用 `o=0`，不能与直接切 latent 视为逐值一致。

## 4. `ApplyMiniMaxH3MotionContext`：另一套端点语义

证据：`HermesH3Continuation/__init__.py` 的 `ApplyMiniMaxH3MotionContext.apply`、`_boundaries`。

| 项目 | 当前 Apply 行为 |
| --- | --- |
| 输入 | `positive, samples, context_samples, context_frames, continue_audio, audio_context_frames, context_end_frame`；默认分别涉及22帧视频、开启音频、24帧音频、端点1。端点须显式连接／设置。 |
| 源窗口 | `[E-C,E)`，`C=context_frames`；检查 `1<=C<=E<=F`，两端必须都在按 `(1,4,4,4,4)` 累加的视频 token 边界上。 |
| 头部预留 | `trim=ceil(C/17)*17`，`guide_start=trim-C`；`trim` 必须小于目标总帧数。 |
| 视频注入 | 一个 keyframe，`resolved_frame_index=guide_start`，latent 为该 token 区间；不是原生路线的逐 token 多块 marker 布局。 |
| 音频注入 | `a=min(audio_context_frames,C,trim)`；开启且 `a>0` 时，`audio_end=round(E/24*40)`，`audio_len=round(a/24*40)`，切 `[audio_end-audio_len,audio_end)` 放入该 keyframe 的 `audio_latent`。 |
| 输出 | 修改后的 positive、原目标 samples、trim。已有 keyframes 取自 positive 首项并追加；不采用原生路线的冲突锚点筛选。 |

**C=22 时，Apply 返回 trim=34、guide_start=12；音频参数24被截到22帧，得到37步，而不是40步。**这不能替代本模板的“实际裁22帧”路线。Apply 确实读取 E，但 token 边界不对齐会拒绝；仅在 metadata 写入 published-end 不能绕过这一限制。它不写两个 Motion Context marker，不安装下面的补丁，也不能假设补丁会自动替它修正中间锚点／Ref2VA payload。是否由所装 Comfy 原生支持这种 guide，需要另验。

## 5. 解码后 Trim：头尾与音频公式

两者都作用于已解码 `images` 与 `audio["waveform"]`，不修改 canonical latent。设 `N=images.shape[0]`、音频采样率 `sr`、帧率 `fps`。

| 行为 | `TrimMiniMaxH3MotionContext` | `MiniMaxH3MotionContextTrim` |
| --- | --- | --- |
| 字段 | 必需 `images,audio,trim_frames,visible_frames,fps` | 必需 `images,trim_frames`；可选 `audio,fps,match_tail` |
| 视频 | `s=int(trim_frames)`，`e=s+int(visible_frames)`，输出 `images[s:e]`；`N<e` 报错 | `n=max(0,int(trim_frames))`，输出 `images[n:]`；`n>=N` 报错 |
| 音频头 | `a=round(s/fps*sr)` | `cut=round(n/fps*sr)`，先取 `waveform[...,cut:]`；cut 耗尽音频时报错 |
| 音频尾 | `b=round(e/fps*sr)`，输出 `waveform[...,a:b]`；原音频不足 b 报错 | `match_tail=True`（默认）：令 `want=round((N-n)/fps*sr)`，长则截到 want，短则尾部补零到 want |
| `match_tail=False` | **没有这个字段**，也没有补零逻辑 | 只裁音频头，保留剩余尾长，可能仍与视频时长不等 |
| 发布长度 | 同时定长选取 visible 区间 | 无 `visible_frames`，仅去头；需要另一显式 AV 定长裁切才能得到本模板的发布长度 |

左列音频样本数是 `round(e/fps*sr)-round(s/fps*sr)`，不可擅换成 `round((e-s)/fps*sr)`；分别四舍五入在部分参数下可相差一个样本。右列 match_tail 是裁去头以后按剩余帧数校尾，不是选择 source context 尾端的参数。

例：24fps、sr=32000、裁22帧，音频头切点是29333样本。模板第二段的定长 Trim 取视频 `[22,180)`，尾部12帧仍留在 canonical；192与158的差34不能统一当作头部 trim。`fps` 必须与解码视频及封装设置一致，不能用音频 latent 的40Hz替代。

## 6. 配套 patch 与注册入口要求

- `nodes.py` 通过相对导入使用 `patch_layout.py` 和 `patch_payload.py`，不能只复制一个同名类文件。layout 在首次调用时经 `_ensure_layout_patch` 安装；带音频时会经 `_ensure_payload_patch` 安装 payload patch。**导入成功或节点显示出来，不证明补丁已生效。**
- `patch_layout.py` 的 `_fixup` 将带 `motion_context_index` 的视频 cond 放到正确目标位置；`_fixup_audio` 根据 segment 表只平移带 `motion_context_audio_end_frame` 的音频 reference。音频标记块要求恰好一个，其 stereo rows 数量应为 `2*r`，不能移动所有音频 reference。
- `patch_payload.py` 的 `_patched_extra_conds` 在 keyframes 与 refs 共存且有上述 marker 时，将视频 payload 按“keyframe视频、reference视频”顺序拼接，音频同理，避免 refs 覆盖 keyframe 内容。未带 marker 的 Apply 不触发该修复分支。layout 有位置而 payload 无内容仍会失败。
- 两个 marker 字符串是节点／两补丁共享的接口，不能独立改名。layout patch 探测 `PackedLayout.__init__` 是否接受 `frame_count`，而不是仅相信版本字符串；源码注释提及不同 Comfy 版本，不代表本页已固定或验证那些版本。
- 补丁包含重复／其他包装器检测。遇到另一副本时可能让先加载的副本接管；因此 `is_applied=True` 仍不能证明正在用这里的 SHA。检查真正生效的函数来源；不要叠装多个副本或仅靠重命名文件夹禁用。
- 注册入口补查：现已从安装目录取回原生包的 `__init__.py`，核对其上游为 NikoDemon80/ComfyUI-H3-Motion-Context，详见[完整来源与版本边界](node-sources.md)。旧缓存目录缺入口不等于无法恢复完整包。当前安装含本地修改且不是历史版本锁；仍须在目标实例核对 `/object_info` 的真实 API 类名与字段。

## 7. 社区复现者对照清单

以下是可逐项操作的检查，不是声称读者已安装相同实现；不要导入来源不明的 Python 文件来“只查字段”。

- [ ] 对自己安装的四个逻辑文件计算 SHA-256（例如在已确认的对应包目录执行 `shasum -a 256 __init__.py`，或 `shasum -a 256 nodes.py patch_layout.py patch_payload.py`）。记录实际包版本／commit；不匹配时按实际源码重新审查，不能只对齐节点名称。
- [ ] 在自己的 Comfy 实例读取 `/object_info`，核对 Save/Load、Motion Context、Trim 的 API 类名、字段及返回顺序。检查包顶层注册和补丁实际加载来源；检查首次调用日志中的失败／重复副本提示。
- [ ] 用自己信任的 safetensors 读取器在 CPU 查看 tensor keys、shape、dtype、metadata：确认两路 batch、24视频通道、32×2音频通道以及 `Ta=round(F/24*40)`。另验 `[s,E)` 与 `E=s+V`；保留前驱文件 SHA。不要把普通列表 Load 输出接解码器。
- [ ] 检查实际提交图：前驱完整 canonical 接 `context_latent`；目标 `latent` 与 conditioning 属于同一目标长度／画布。原生路线不应伪接 `context_end_frame`；如选 Apply，应将其作为不同实验，显式设置 E 并验证 token 边界。
- [ ] 对22帧原生窗口核对7个源 token、起点周期相位0、目标锚点 `0,1,5,9,13,17,18` 和返回 trim22；音频24帧核对40步及补偿后的结束坐标。若是 Apply，应核对 trim34、guide_start12、音频37步，不得把两份日志称为同一参数运行。
- [ ] 在 layout／payload 检查中确认原有 Ref2VA references 保留、只有标记音频块被移位、视频和音频 payload 顺序与 segments 一致。相同 seed 或 metadata 不代替此项。此检查需要受信实现的诊断能力；本页不提供可冒充验证结果的实现代码。
- [ ] 同时保留 canonical 解码与发布 AV，按第五节公式计算帧区间和音频样本区间。可用 `ffprobe -v error -count_frames -show_streams -of json clip.mp4` 核对实际帧数／帧率／音轨；容器时长或有损音频编码后的包时长不是精确 waveform 样本数，后者应在封装前另记。
- [ ] 自行完成一次受控续接及边界试听／观看，记录真实图、版本、模型／输入／输出 SHA、源窗口、trim 和音频长度。技术形状相容不证明人物、动作或声音连续；公开记录前移除私人路径及运行标识。

## 8. 当前源证据与未决项

下面是本次对当前回收文件实际计算的 SHA-256。逻辑文件名用于定位语义，不表示可从某个已固定公开包下载相同字节。

| 逻辑文件名 | 定位入口 | 当前 SHA-256 |
| --- | --- | --- |
| `HermesH3Continuation/__init__.py` | `_av`；Save／Load／Apply／Trim 四类；`NODE_CLASS_MAPPINGS` | `edf270a641808282f5d3ff51a260518821a59ad1dffcd27e23e6f6794787c573` |
| `h3_motion_context/nodes.py` | `MiniMaxH3MotionContext.apply`；尾窗口 helpers；另一套 Trim／Save／Load；`NODE_CLASS_MAPPINGS` | `a55a99aeb9c223e33e7adf2f6ae456726903db07e61e08418aa7e62ea9d9cc97` |
| `h3_motion_context/patch_layout.py` | `_fixup`、`_fixup_audio`、`_target_origin`、`apply_patch` | `302b13b42bc6d9440e54d8030a22828a5f8b84b10c9c6727cdfcac583c6a6840` |
| `h3_motion_context/patch_payload.py` | `_patched_extra_conds`、`apply_patch` | `0b05b6ac154044bd4abad7ac7236a3bd9b1e9c887a74170f9bf44e182a07ce49` |

尚未解决：源包来源与许可链、可公开分发的固定版本、右列包顶层入口、历史运行源码与当前文件的对应关系、历史 Comfy／模型环境锁，以及读者环境的真实运行验证。本页提供精确语义作为复现对照，不以当前源码倒填历史证据，也不以文档替代安装器或端到端复现结果。
