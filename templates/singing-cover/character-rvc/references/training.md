# 素材筛选、特征、训练与索引

本页面向用户指定角色；莫斯提马中文只是[历史对照](validation.md)。训练不是从台词文本合成声音，不需要 ASR 全文或把字幕喂给 RVC。

## 1. 来源与原件

先走[来源发现协议](discovery.md)：原生官方/可信网页搜索，必要时站内元数据兜底，核对候选后再决定是否取得素材。身份、作品、语言、CV、权利依据分别记录；下载/训练/发布并非同一种授权。资料站或转载合集不自动变成官方。

取得本次有权使用的材料后，保留原媒体与白名单元数据，再生成新解码文件；平台有损流转 WAV 不恢复损失。这里不提供绕过平台限制、cookies 或自动下载所有候选的流程。

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,sample_rate,channels -of json "$SOURCE"
ffmpeg -hide_banner -n -i "$SOURCE" -map 0:a:0 -ar 48000 -ac 1 -c:a pcm_s24le "$NEW_DECODED"
```

这一步可统一解码规格；保存原通道信息、变换实参和源/输出 SHA，不把解码后 48k 单声道说成下载原流规格。每次输出必须新文件。

## 2. 筛选和分组留出

建立私有 `dataset_manifest.json`：`source_id`、来源 URL、语言/CV 判断、录音哈希、原采样率、源半开时间/样本区间、派生片段哈希、处理方法、分组 ID、split、纳入/排除理由。文本标签可简短描述，不公开逐句转录。逐片人工审听确认同一目标说话人；排除其他角色、解说、错误语言、合唱、BGM 过重、剪辑接缝、削波、强混响、重复和无有效发声材料。降噪/去混响只保留为候选，有损字词或音色时用原版，不能默认全量处理。

先统计原始录音、实际有效语音、训练切片总长；有重叠切片时另记去重覆盖时长，不能片数乘 3.7。对白缺乏歌唱高音/长音，不能靠加 epoch 补齐信息。原始素材只有几分钟时可以探索，但先声明数据规模和音域覆盖限制。

**先分组再切片：**按独立原始录音、同一句台词的多个导出/版本及近重复内容组成 group，整个 group 只进 train 或 holdout。可将约 10%–20% 的组作为初始留出方案，实际比例由数据规模/覆盖决定，不是已验证最佳比例；保存 seed、分组映射和真实时长。不能将同句重叠窗随机拆分后声称无泄漏。

只有单条合集时：尽可能按原台词/录音边界划组并防止相邻重叠窗口跨 split；同一录制环境仍相关，无法得到严格独立的泛化证据。没有足够独立材料就明确写“内部留出代理/独立验证不足”，不要编造历史验证集。单独保留覆盖辅音、高音、弱音、长音和和声重叠的授权演唱短段作为转换探针，不能混入训练素材。

物理隔离 `JOB/data/train` 与 `JOB/data/holdout`，只把已批准 train WAV 放进前者；清单不放在会遍历所有文件的输入目录里。**holdout 不进入预处理训练输入、训练 filelist 或检索特征索引**。后续源内容变化使派生特征和训练结果失效，用新实验，不覆盖旧缓存。

## 3. 预处理：per 不是 threshold

完成[部署](deployment.md)后，操作者绑定 `EXP`、`GPU`（已获分配的物理设备 ID）、`RVC_APP`、`RVC_PY`、`JOB`。在 Bash 严格模式下逐段执行；下列数值是固定路线起点，不是硬件普适最优参数。

```bash
cd "$RVC_APP"
EXP_DIR="$RVC_APP/logs/$EXP"
test ! -e "$EXP_DIR"
mkdir -p "$EXP_DIR"
"$RVC_PY" -m train.preprocess "$JOB/data/train" 48000 8 "$EXP_DIR" False 3.7
```

位置参数依次为：输入目录、目标采样率、进程数、实验目录、`noparallel=False`、**`per=3.7` 秒**。该脚本直接读取 `sys.argv`，不能假设支持 `--help`；需读固定源码核对。开始前创建实验目录，因为日志文件打开早于内部目录创建。

| 处理 | 固定源码行为 |
| --- | --- |
| 加载 | `load_audio(..., force_mono=True)` 默认单声道 |
| 高通 | 5 阶 48 Hz，`signal.lfilter`，不是零相位 filtfilt |
| 静音切分 | threshold=-42 dB；min_length=1500 ms、min_interval=400 ms、hop_size=15 ms、max_sil_kept=500 ms |
| 分块 | per=3.7 s、overlap=0.3 s、步进=3.4 s；剩余不大于 4.0 s 时整个尾段写出 |
| 异常门槛 | 峰值非有限、<=0 或 >2.5 跳过；不是语言/声纹检查 |
| 归一化 | `x/peak*(0.9*0.75) + (1-0.75)*x`，不是 LUFS 归一化 |
| 输出 | `0_gt_wavs/*.wav` 为 48k FLOAT；`1_16k_wavs/*.wav` 为 16k FLOAT |

min_length 不保证最终每块至少 1.5 秒，尾块可以更短；历史 0.62 秒片段就是例子。预处理捕获部分异常后仍可能退出 0，必须看失败日志、实际数量与解码。FLOAT WAV 应用 SoundFile/ffprobe 检查；标准库 `wave` 报 format 3 不足以证明损坏。

## 4. F0 与 768 维特征

```bash
CUDA_VISIBLE_DEVICES="$GPU" "$RVC_PY" -m train.dataset.extract_f0 cuda 1 0 "$GPU" "$EXP_DIR" True
CUDA_VISIBLE_DEVICES="$GPU" "$RVC_PY" -m train.dataset.extract_hubert_feature cuda 1 0 "$GPU" "$EXP_DIR" v2 True
```

F0 位置是 `mode, n_part, i_part, i_gpu, exp_dir, is_half`；HuBERT CUDA 版本还带 `v2`。脚本会用 `i_gpu` 设置 CUDA_VISIBLE_DEVICES，它不是 GPU 数量；设备分区含义为 1 份中的第 0 份。不要套另一个版本的旧 CLI。

CUDA F0 固定 RMVPE，16k 输入，hop=160，`thred=0.03`；全零音高可能跳过，结果分别为 `2a_f0/<id>.wav.npy`（粗 F0 1..255）和 `2b-f0nsf/<id>.wav.npy`（连续 F0）。HuBERT 16k、hop=320，v2 输出 `3_feature768/<id>.npy`。两者帧率不同，不要求 HuBERT 帧数与 F0 原始长度相等；训练 loader 会作对应对齐，但明显时长错配须先修复。

这些脚本按存在文件跳过，不会自动校验缓存与新输入一致。运行前检查 run_guard；输出后检查日志中失败/跳过原因、读取数组 `allow_pickle=False`，验证 feature 为非空 `N x 768`、全部 finite，F0 两数组非空一维且长度匹配、粗 F0 范围/整数性、连续 F0 范围；音频实际 48k/16k、单声道、非空有限。不能靠扩展名判断上述条件。

## 5. 四路交集与两条 mute

在**实际 RVC 文件系统**上运行 helper，`RECIPES_ROOT` 指向该处 Recipes checkout：

```bash
python3 "$RECIPES_ROOT/templates/singing-cover/character-rvc/scripts/build_filelist.py" \
  --experiment "$EXP_DIR" --mute-root "$RVC_APP/logs/mute" \
  --output "$EXP_DIR/filelist.txt" --report "$JOB/filelist-report.json"
```

四路以同一 ID 相交：`0_gt_wavs/id.wav`、`3_feature768/id.npy`、`2a_f0/id.wav.npy`、`2b-f0nsf/id.wav.npy`。每行是 `wav|feature|coarse_f0|continuous_f0|0`。只做单说话人 0、v2/48k/F0，不能拿参数省略来混入 v1/40k/多说话人。

默认遇缺失模态失败并报告缺失 ID，不写结果；读日志确认缺失原因后可在**仍不存在的新输出路径**加 `--allow-incomplete` 接受交集排除。不允许空交集、空文件、符号链接、不安全路径分隔符、缺失 mute、同输出与报告路径、覆盖旧文件。忽略 `.spec.pt` 缓存，不把它算 WAV。

报告 `character_rows`、`mute_rows=2`、`total_rows`、各模态计数、缺失清单和输入/列表 SHA；两条 mute 是同一个 48k/v2 占位行重复两次，不算两条角色语音。列表按 seed 20260731 固定洗牌，仅为确定性输出；训练 seed 由配置另控。**helper 不读取 NPY 内容、不解码 WAV、不自动验证留出隔离**，第 4 节检查仍必须做。不要把未读文件内容的通过称为训练集质量通过。

历史中文：87 个 gt/16k/HuBERT，F0/NSF 各 86，`0_61.wav` 全零 F0 被排除，88 行=86 角色+2 mute。87 段共 194.82 秒，86 交集共 194.20 秒；不是 86 段 194.82 秒。

## 6. 训练与 checkpoint 选择

将固定 `configs/v2/48k.json` 复制到新实验的 `config.json`，先确认目的不存在；保留原模板与最终配置字节和差异。`assets/weights` 父目录在部署阶段已创建。按实际显存设置 `BATCH`；以下保留历史 batch16/200 epoch/每50保存的路线作为可调整起点：

```bash
test ! -e "$EXP_DIR/config.json"
cp -n "$RVC_APP/configs/v2/48k.json" "$EXP_DIR/config.json"
CUDA_VISIBLE_DEVICES="$GPU" "$RVC_PY" -m train.train \
  -e "$EXP" -sr 48k -f0 1 -bs 16 -g "$GPU" -te 200 -se 50 \
  -pg assets/pretrained_v2/f0G48k.pth -pd assets/pretrained_v2/f0D48k.pth \
  -l 0 -c 1 -sw 1 -v v2
```

`-l 0` 不仅保留最新；`-c 1` 缓存训练集到 GPU；`-sw 1` 导出小模型；`-te 200` 总 epoch；`-se 50` 保存间隔。OOM 时先确认进程已退出，再以新配置降低 batch 或 `-c 0`，记录版本分支，不能在健康训练旁重复启动。小数据也不保证缓存合适。

模板 `train.seed=1234`、learning_rate=0.0001、segment_size=17280、hop_length=480；模板 epochs=20000/batch_size=4 不是 CLI 的实际 200/16。保存实际 hparams、CLI、日志、退出码、耗时和各保存点，不能仅从模板推断运行参数。steps 受 loader/bucket/恢复等影响，不用 `ceil(rows/batch)` 强推文件名步数。

`logs/$EXP/G_*.pth` 与 `D_*.pth` 是训练/优化器恢复档；`assets/weights/*.pth` 是小推理模型，不能互相替换。核对配对保存步、日志和 hash；目录缺失造成小模型导出失败时，先恢复导出而不是重训已健康保存的 G/D。上游训练可能自动寻找最新 G/D，恢复必须按[恢复页](repair.md)审查配对与阶段输入。

每个候选 checkpoint 在**同一组留出对白+授权演唱探针**、同一源分轨/索引/参数下比对：角色音色、字词与辅音、弱音/呼吸、高音稳定、长音纹理、过拟合痕迹及技术指标。记录实际文件 SHA、参数、听审结论、拒绝原因；保持最终测试组不被反复调参污染。loss 不是音色评价函数，最晚 epoch 不自动最好。

历史中文脚本训练至 e200，然后硬编码选择 `e150_s1200`，没有独立验证集或完整 checkpoint 听审矩阵。新训练不得把 e150 当默认最佳，也不能凭 glob 排序自动选模型。无法听审时只能交付候选。

## 7. 索引集合、新鲜度与 added

索引来自内容特征，不来自生成器 epoch。固定上游 `train_index.py` 读取实验目录的**全部** `3_feature768` 文件，不按训练 filelist 再求 F0 交集。历史中文为 **87 份 HuBERT、9684 x 768、IVF248/nprobe1**，不是 86 个训练样本；缺 F0 的内容特征仍进入历史检索。新方案可以选择只索引训练交集，但必须显式创建独立索引实验、记录选择与哈希，不能描述成历史已如此执行；两种方案均不得含 holdout。

在冻结特征、不再有写进程时建立 `index-inputs` spec/receipt，至少绑定全部特征成员/bytes/SHA、HuBERT 配置/权重、源码与 v2 参数。确认本次索引工作目录和外部索引目录没有旧 `trained_*.index` 或 `added_*.index` 后执行：

```bash
"$RVC_PY" -m train.train_index "$EXP" v2 "$RVC_APP/assets/indices" 16
```

上游遇已有 added 会直接跳过，且可能复用已有 trained；**存在和 mtime 都不证明新鲜**。输入变化或无可靠旧 receipt 时，用新索引实验名与新的特征目录重建，保留旧文件，不删除旧索引来“修复”。真实 added 常在 logs，assets/indices 是软链接；run_guard 拒绝链接，spec 请绑定解析后的真实文件。

算法拼接特征，超过 200000 行时尝试 KMeans 到 10000 中心，失败可回退原特征；`n_ivf=max(1,min(int(16*sqrt(N)),N//39))`，每 8192 行添加。验证实际矩阵、构建日志与 `d=768 / is_trained / ntotal`，不能仅从 IVF 文件名断言内部属性。随机排列/KMeans 不保证每次 index 字节一致，保存本次实际 hash，而不是强求等于历史模型索引。

推理必须使用 **added**（已加入向量），不是仅训练聚类结构的 trained。记录小模型的角色/语言/版本/F0/48k 和索引数据来源、维度、hash；参数/特征不变时换同一训练支线 epoch 不必重建索引，但仍要重新做配对与短段听审。
