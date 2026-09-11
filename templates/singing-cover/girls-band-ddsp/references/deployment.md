# 部署与兼容组合

## 本机控制，Linux GPU 推理

本机管理源文件、哈希、参数、上传/提交、状态、取回与听审；分离和 DDSP 在自己配置的独立 Linux NVIDIA GPU 环境执行。SSH 主机别名、认证、GPU 分配均由操作者在模板外设置，不写进公共配置。不在 macOS 安装 CUDA lock 后声称已适配 MPS；此次没有验证 MPS、GPU 型号最低要求或峰值显存。

历史基线如下，是恢复参照，不是本次部署结果：

| 层 | 固定组合 | 注意 |
| --- | --- | --- |
| DDSP | 6.2，commit `aeaba53f46fbb4e8177af444c5c56660f55b1787` | 资料原部署缺 `.git`，未证明完整源码逐文件等于该提交 |
| Python / Torch | Python 3.10，torch/torchaudio 2.4.1+cu121 | Linux CUDA 12.1 wheels；驱动兼容性在新主机验证 |
| 关键依赖 | setuptools 80.9.0、numpy 1.26.4、fairseq 0.12.2 | 不是完整 lock；其余依赖按固定源码恢复并保存实际 lock |
| 分离 | pymss 2.0.14、pymss-core 0.1.4 | 与 DDSP 隔离环境；不用自动更新的 catalog 替换历史配置 |
| vocoder | PC-NSF-HiFiGAN 44.1k/hop512/128bin 2025.02 | checkpoint 与 config.json 同发行配对 |

历史 DDSP app 内 `uv.lock` SHA-256 为 `ad9c8bd4ea171aba99d2963c6cd032208b53e787ddd9166d53f92e792b5a1d6a`，pymss app 内 lock 为 `59750deea43983789219d9ded2e265babdf1720a45a8fd119c88a563d3b93d5f`。本模板不附私有环境 lock，不能仅靠这两个哈希恢复完整环境。没有可信旧 lock 时生成并记录新 lock、安装版本和 smoke 结果，标为新环境验证，不伪称精确还原。

在新目录获取固定代码，保留 `git rev-parse HEAD` 与干净状态；如果与历史入口有差异，先 diff 再决定迁移。已有可信匹配 `pyproject.toml`/`uv.lock` 才可在相应 Linux 项目中 `uv sync --frozen --python 3.10`。不要覆盖共享环境临时升级依赖。本模板没有自动安装器。

## 模型库

预检参数 `--model-root` 指向自己新建的模型库；清单路径均相对该根目录：

```text
MODEL_ROOT/
  voices/<voice-id>/model.pt
  voices/<voice-id>/config.yaml
  pretrain/contentvec/checkpoint_best_legacy_500.pt
  pretrain/rmvpe/model.pt
  pretrain/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02/model.ckpt
  pretrain/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02/config.json
  separation/vocal/vocal_extraction/bs_roformer_voc_hyperacev2.{ckpt,yaml}
  separation/karaoke/bs_karaoke_gabox_IS.{ckpt,yaml}
  separation/reverb_echo_control/dereverb/Lead_VocalDereverb.{ckpt,yaml}
```

`{ckpt,yaml}` 是说明中的简写，不是实际文件名。角色来源在 [voices.json](../model-catalog/voices.json)，依赖的固定发行及文件哈希在 [dependencies.json](../model-catalog/dependencies.json)。只下载有权取得的文件到隔离 staging，安全解压（拒绝绝对路径、`..`、越界链接），不执行包内未知程序。不要把 LFS 指针或未下载完的 `.part` 当权重。

匹配完整大小/哈希才入库；`bytes: null` 只是不额外断言大小，仍必须匹配 SHA-256。不要为让预检通过改清单。八个角色原 config 均为 1172 字节且哈希相同，保留 CRLF 原字节；仍需逐角色配对，不混用训练 step。`model_30000.pt` 等原文件可在验证后规范命名 `model.pt`，不能以同名认身份。

预检拒绝模型库外的 symlink 目标；库内合法链接可用。DDSP 源码目录的 `pretrain/` 可以显式指向这份库的 `pretrain/`，但这属于部署操作：核对实际 resolve 目标与哈希，勿让 `ln -sfn` 在已有目录里面悄悄嵌套链接。`PYMSS_MODEL_DIR` 指向模型库中的 `separation/`。DDSP 从 checkpoint 邻接的 `config.yaml` 读取配置，不提供臆造的 `--config` 标志。

**已知坏副本：**资料记录去混响 checkpoint 曾只有 255995904 字节，完整文件应为 913031195 字节，哈希也不同。资料后续远端完整副本字节通过，不会使本地坏副本变好；缺失或不匹配必须拒绝加载。不要对不可信 `.pt/.ckpt` 做 pickle 反序列化来“检查 step”。

## 配置含义

| 字段 | 这批配对配置值 | 边界 |
| --- | --- | --- |
| sampling_rate / block_size | 44100 / 512 | 输出时间基准仍按真实伴奏 frames 校准 |
| encoder | contentvec768l12tta2x | legacy 500，不是 6.3 的同类文件 |
| encoder 输入 / 通道 / hop | 16000 / 768 / 160 | 不等于最终导出采样率 |
| f0_extractor / 范围 | rmvpe / 65–800 Hz | 配置范围不是训练覆盖保证；CLI 需显式传值避免默认 50–1100 |
| type / n_spk / speaker ID | RectifiedFlow / 1 / 1 | 角色 checkpoint 各自独立 |
| infer_step / method | 50 / euler | 是推理步数，不是角色名中的训练 step |
| use_pitch_aug | true | 不是任意移调质量保证 |

6.3、RVC、Mostima 自训练支线不在本模板兼容范围。不要把教程未明的“强度”值猜成 `t_start`。

## 真正的运行入口

公开版没有私有 `svc-job`、`run_ddsp.py` 或 `run_mix.py` 执行器。资料中语义 job YAML、runner stages/argv YAML、两阶段 shell 是三个不同契约；不能把任意 job 文件交给一个不存在的 CLI。

[处理说明](processing.md)提供的是已对照资料中的 pymss 2.0.14 用法与 `main_reflow.py` argparse 核实过的命令片段。新部署还要运行安装版本的帮助并比对；入口漂移时停止，不猜参数。DDSP 帮助可能先导入 ML 依赖，因此它不能替代标准库离线预检。

每个作业使用唯一目录和输出名；启动前取得自己环境中的调度锁，绑定 GPU。断开 SSH 后核查同一 PID/日志/输出哈希再续跑；不随便终止他人进程，不执行带删除语义的同步。
