# 分离、转换、混音与交付

本页命令需在已完成部署、获得授权及独占作业输出目录后执行。变量均由操作者绑定真实绝对路径，禁止照搬历史服务器参数。没有自带自动执行器，不能将这些片段视为无人审听的一键脚本。

## 1. 输入绑定

为每次运行建立唯一 ID，保存 source 文件 SHA、来源、真实编码、角色、原调/移调、父版本、运行版本与状态。输出按阶段编号：`01_vocal`、`02_candidates`、`03_dereverb`、`04_canonical`、`05_converted`、`06_mix`、`07_delivery`。原始源和已完成目录只读。

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels,bit_rate -of json "$SOURCE"
ffmpeg -hide_banner -n -i "$SOURCE" -map 0:a:0 -ar 44100 -ac 2 -c:a pcm_s24le "$SOURCE_WAV"
```

`SOURCE_WAV` 必须是新输出路径；MAC 使用 `shasum -a 256`，Linux 可用 `sha256sum`。文件名的“无损/Hi-Res”不是格式证据，AAC 转 PCM24 不会恢复已丢信息。复用 stems 时也记录输入哈希、共同起点和精确 frames，不能仅凭文件名推测它来自哪版歌曲。

## 2. 三阶段分离

`CHOSEN_GPU` 是已获分配的 GPU，`PYMSS` 是隔离环境中实际可执行文件。完成外部调度/锁以后：

```bash
export CUDA_VISIBLE_DEVICES="$CHOSEN_GPU"
export PYMSS_MODEL_DIR="$MODEL_ROOT/separation"
"$PYMSS" infer bs_roformer_voc_hyperacev2 -i "$SOURCE_WAV" -o "$VOCAL_DIR" --device cuda --device-id 0 --format wav --wav-bit-depth PCM_24
"$PYMSS" infer bs_karaoke_gabox_IS.ckpt -i "$TOTAL_VOCALS" -o "$CANDIDATE_DIR" --device cuda --device-id 0 --format wav --wav-bit-depth PCM_24
"$PYMSS" infer Lead_VocalDereverb.ckpt -i "$CANDIDATE_A" -o "$DEREVERB_A_DIR" --device cuda --device-id 0 --format wav --wav-bit-depth PCM_24
"$PYMSS" infer Lead_VocalDereverb.ckpt -i "$CANDIDATE_B" -o "$DEREVERB_B_DIR" --device cuda --device-id 0 --format wav --wav-bit-depth PCM_24
```

**逐条执行并绑定上一阶段实际输出后再继续。** 不自动猜 `TOTAL_VOCALS`、A/B 后缀；原始 `vocals/other` 名字保留，canonical 名字在听审后另建。CUDA 可见设备映射后进程内编号为 0。pymss 模型是位置参数，不是 `--model-id`；格式为 `--format`，不是 `--output-format`。

### 人工关口 A：声部与去混响

对两个候选的 raw/noreverb/reverb 分别检查：歌词是否完整，主旋律是否连续，和声及呼吸是否被吞，RMS、多门限（如 -50/-40 dB）活动时长、F0 活动和听感。比较相同测量方法下的去混响活动保留率；raw 无活动时比例记不可计算，不除零。

不要取 integrated LUFS 较高者自动当主唱：稀疏和声可能因响度门控看起来更响。不要按名字判定 `noreverb` 必然可用。历史《让风告诉你》主唱保留率约 0.9972，和声约 0.4579，因此主唱用去混响、和声保留 raw；这是该歌的决策，不能照抄到 Starboy 或 Billie Jean。

保存 `stem_semantics.json`：候选文件/哈希、lead/backing 身份、raw 或 noreverb 选择、测量、审听人/时间、决定理由。未审听写 `pending`，不自动通过。允许先输出候选供听审，不直接批量整曲转换。

### 配置漂移风险

pymss 2.0.14 的 Gabox target stem 记录为 `backing_vocal`，后续快照为 `vocals`；dereverb 由 `reverb` 变为 `noreverb`。HyperACE 原作者 YAML 的 `num_overlap: 4` 与部署镜像 `overlap_size: 48000` 不是可互换字段；Gabox 为 `num_overlap: 2` 对 `overlap_size: 17640`。恢复用清单配对 YAML，保留双路，不靠标签猜方向。部分上游 YAML 有 `!!python/tuple`，不为绕过安全解析错误而启用任意对象的 unsafe loader。

## 3. 分声部 DDSP

先用审听过的短段（建议 10–20 秒，覆盖弱音、高音、辅音和重叠处）检查 F0 P05/P50/P95/P99，再用相同参数整曲。以下直接调用已核对的 6.2 入口，不是私有 wrapper 命令；`DDSP_PYTHON` 是对应 Linux 隔离环境 Python，`VOICE_MODEL` 指向选定角色 `model.pt`，邻接配置必须匹配。

```bash
cd "$DDSP_APP"
"$DDSP_PYTHON" main_reflow.py -m "$VOICE_MODEL" -i "$DRY_LEAD" -o "$NEW_LEAD_OUTPUT" -d cuda -id 1 -k 0 -f 0 -v 0 -pe rmvpe -fmin 65 -fmax 800 -th -60 -step 50 -method euler
"$DDSP_PYTHON" main_reflow.py -m "$VOICE_MODEL" -i "$DRY_BACKING" -o "$NEW_BACKING_OUTPUT" -d cuda -id 1 -k 0 -f 0 -v 0 -pe rmvpe -fmin 65 -fmax 800 -th -80 -step 50 -method euler
```

输出目录必须新建且目标文件不存在，上游入口不提供通用的禁止覆盖参数；由作业所有者在持锁情况下检查。保存实际 argv、退出码、日志、耗时和输出哈希。不能用本说明的命令行替代实际日志。

- `-k` 改旋律音高；先原调 0，不因男声转少女音色固定 +12。
- `-f` 是 formant 条件，`-v` 是对应 PC 路线的 vocal register 条件，不是相同控制。此处均 0；新值单变量测试，检查源码实际是否应用。
- `-th` 是活动门限，不是音量。主唱 -60、和声 -80 是起点；历史和声有 -75 净化与 -85 增强分支，不是全局默认。
- `-step 50` 显式指定推理 steps。角色训练 step 不由它改变。使用短参数 `-th` 避免把源码中的拼写 `--threhold` 猜写为 `--threshold`。
- 配对 config 的 `vocoder.type` 写 `nsf-hifigan`，实际 ckpt 路径才固定到 PC 2025.02；不凭类型字符串换权重。

### 人工关口 B：先干声再全曲

审听目标音色、辅音、字词、高音、弱音、掉句、颤音、呼吸和多声冲突。对齐共同有声 frames 才比较输入输出 F0 移调；不能比较两个不同活动区的全局中位数。技术指标不能替用户签字确认“像角色”。干声错字先修声部/模型/F0/音素，不靠混响遮住。

按伴奏真实采样率和 frame count 对齐所有转换 stems。DDSP 可能产生块尾 padding，不固定假设多 64 samples；记录每轨裁尾/补零，检查头部偏移与内部漂移。大幅长度不符先排错，不能整轨强行拉伸或静默补齐。保存转换原件与对齐版各自哈希。

## 4. 混音与母带

先保留完整 dry stems。可用 DAW 或自行审查的 FFmpeg 链：资料 `tutorial_simple` 是 HPF + aecho + gain，而 `baseline` 另有 EQ/压缩，不能说所有歌都用了全套效果。历史主唱 HPF70 Hz、延迟40/85 ms；和声 HPF110 Hz、延迟45/95 ms。FFmpeg aecho 只是延迟空间感，不等效专业混响或 Audition 插件。

每版重新测原伴奏与原总人声的响度关系，再测实际 FX 后主唱/和声。先设和声相对主唱的策略，叠加测人声总线，再恢复原总人声/伴奏关系；不要复制别的角色 gain。历史《让风告诉你》选择和声约低 9 dB、人声总线前推 1.5 dB；最终伴奏 -6、主唱 +3.6、和声 +1.8 dB 只属于该版。两轨 gain 正负不代表它们最终谁更响。

保存 `mix_balance.json`、实际滤镜/插件、gain、FX 打印、premaster。FX 尾声裁到规范长度前确认不截断目标结尾。先检查 premaster 无削波/有限值，再做两遍 `loudnorm`；-14 LUFS-I / -1.2 dBTP 是本项目预览目标，不是全平台强制标准。

两遍处理先分析 **同一 premaster**，将第一遍 `input_i/input_tp/input_lra/input_thresh/target_offset` 分别写入第二遍 `measured_I/measured_TP/measured_LRA/measured_thresh/offset`。两遍使用相同 I/TP/LRA 目标，保存实际 linear/dynamic 模式，第二遍显式导出 44100 Hz 双声道 PCM24。缺任一测量值不得编造；FFmpeg 4.x 若发生声道布局问题，可在滤镜链显式 `aformat=channel_layouts=stereo`，再真实渲染验证。

真峰值过冲时在新版本明确降低 render target/加守护余量，重新两遍处理及复测；不拿第一遍预测值当最终结果。响度归一化可能改变全曲，因此局部样本不变断言放在母带前 stem 层。

## 5. 人工关口 C 与交付

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels,bits_per_raw_sample -of json "$FINAL"
ffmpeg -v error -i "$FINAL" -f null -
ffmpeg -hide_banner -nostats -i "$FINAL" -af loudnorm=I=-14:TP=-1.2:LRA=11:print_format=json -f null -
ffmpeg -hide_banner -i "$FINAL" -af silencedetect=noise=-55dB:d=2 -f null -
```

独立响度分析读取最终文件的 **input_i/input_tp**，不是输出侧预测值。静音检测只标记疑点，音乐原有静音不能直接判失败；人工复核掉句和边界点击。另记录 decoded frame count、有限值、样本峰值、LUFS-I、独立 dBTP、实际总长及处理耗时。不能从容器 duration 或样本峰值推导全部通过。

最终交付母带、premaster、对齐伴奏/转换主唱/转换和声、实际参数、映射/修复/谱系、QC 与听审状态、输入输出哈希。两端传输后分别复算 SHA，完整解码取回文件；传输成功不是字节一致的证据。

检查失败只恢复受影响阶段。某条声部阈值变化只重推该声部；只改 gain 只混音；QC 工具缺包只修 QC。源文件、配对模型或 canonical stems 哈希变化时才使对应下游失效。只通过技术检查可交付“待审候选”，不能写“用户已接受”。
