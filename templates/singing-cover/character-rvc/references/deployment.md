# 分阶段部署

这是新环境操作说明，不是已执行日志。默认独立 Linux NVIDIA GPU；macOS 可做元数据、哈希和离线 helper，不声称能照此训练。远程连接由操作者单独管理，本页没有 SSH、凭据、机器地址或固定 GPU 编号。

## 0. 工作目录与停止条件

先在 Recipes 仓库根记录 `RECIPES_ROOT="$PWD"`，再由操作者绑定以下**真实绝对路径**：`RVC_APP`（新源码目录）、`JOB`（新工程目录）、`RVC_PY="$RVC_APP/.venv/bin/python"`。用 ASCII job/实验名，如 `character-zh-rvc-v2-48k-run01`；不要复用历史实验名。输入保存在 job，源码/运行缓存保存在隔离环境。路径不含 `|` 或换行。

新建时检查目标不存在；不覆盖既有源码或实验。建议在 Bash 严格错误模式 `set -euo pipefail` 下逐段运行，下游变量只能绑定上一阶段实际产物。部署、训练和模型下载命令需要网络/硬件，**不是离线测试内容**。

```bash
test ! -e "$RVC_APP"
test ! -e "$JOB"
mkdir -p "$JOB"
git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git "$RVC_APP"
git -C "$RVC_APP" checkout --detach 4338f12c3c28c80b3ac015e2d0df66c41592746d
git -C "$RVC_APP" rev-parse HEAD
git -C "$RVC_APP" status --short
```

HEAD 必须精确匹配；已有 tracked diff 先审查，不自动清理。保存 commit、差异、操作系统、驱动和 GPU 运行信息于私有 job，公共报告不要泄露主机身份。`nvidia-smi` 能列出 GPU 只是驱动可见，尚未证明 PyTorch 或模型可用。显存不足时后续降低 batch/禁用 GPU cache；没有本模板验证过的最低显存值。

## 1. 隔离 Python 与两阶段依赖

固定代码的实际文件名为 **`requirments_cu118_py312.txt`**，必须保留这个原拼写。不要照旧 RVC 教程随手安装 `requirements.txt` 或混入 DDSP 6.2 环境。先检查文件内容，再分两段安装：

```bash
cd "$RVC_APP"
python3.12 -m venv .venv
"$RVC_PY" -m pip install torch==2.7.1+cu118 torchaudio==2.7.1+cu118 --index-url https://download.pytorch.org/whl/cu118
"$RVC_PY" -m pip install -r requirments_cu118_py312.txt
"$RVC_PY" -m pip check
"$RVC_PY" -m pip freeze --all
```

第二阶段原文件有公共镜像 index 配置，且不列 Torch/Torchaudio，不应悄悄升级已配对 cu118 两包。留存实际包清单、安装日志和 wheel 来源；文件中的范围约束不是完整 lock。

关键约束：Python 3.12、Torch/Torchaudio 2.7.1+cu118；NumPy `>=1.26.4,<2`、Transformers `>=4.49,<4.50`、Gradio `>=3.14,<3.15`、setuptools `>=75,<81`（保留 pkg_resources）、FAISS `>=1.13,<2`。pymss 2.0.14/core 0.1.4 是分离相关依赖，不是 DDSP 声线权重。

**Linux 可选依赖失败分支：**历史安装曾因 `nvidia-cudnn-cu11==8.9.5.29` 无匹配 wheel 受阻，使用训练专用派生 requirements 排除可选 `nvidia-*` 与 `onnxruntime-gpu`，保留已验证 Torch CUDA 路径。这是有范围的兼容措施，不是通用删包方案。本次未重建完整历史 lock；遇到此错先记录完整错误、wheel 平台标签和依赖关系，再在新文件中逐项审查变更，保留原文件和 diff。不能忽略整个 pip 错误继续，也不能据此声称 ONNX/MSST 已验证；分离后端需要另行验收。

检查实际 CUDA 运算，而不只看 `is_available()`：

```bash
"$RVC_PY" -c 'import torch,torchaudio,numpy,faiss,transformers,soundfile; print(torch.__version__,torchaudio.__version__,torch.version.cuda); assert torch.cuda.is_available(); x=torch.ones(8,device="cuda"); print((x*x).sum().item()); print(numpy.__version__,transformers.__version__,faiss.__version__,soundfile.__version__)'
ffmpeg -version
ffprobe -version
```

这只验证导入和小张量计算，未证明 HuBERT、RMVPE、FAISS 内容或训练可用。不要把此命令放进无 GPU 的离线 helper 测试。

## 2. 配对资产与可信性

从 [model-catalog/dependencies.json](../model-catalog/dependencies.json) 查来源与历史字节指纹，分别核实许可。新下载应固定 HF revision，保留原 URL、revision、bytes、SHA-256；`main` 可变，不能凭文件名接收不匹配文件，也不要改预期 hash 让检查变绿。原始下载 revision 未恢复时明确标记未知。

```text
RVC_APP/
  assets/hubert_base/config.json
  assets/hubert_base/preprocessor_config.json
  assets/hubert_base/pytorch_model.bin
  assets/rmvpe/rmvpe.pt
  assets/pretrained_v2/f0G48k.pth
  assets/pretrained_v2/f0D48k.pth
  assets/weights/                  # 新训练导出的小模型
  assets/indices/                  # 推理索引入口，真实文件通常在 logs
  logs/mute/0_gt_wavs/mute48k.wav
  logs/mute/3_feature768/mute.npy
  logs/mute/2a_f0/mute.wav.npy
  logs/mute/2b-f0nsf/mute.wav.npy
```

上游公开资产入口为 [lj1995/VoiceConversionWebUI](https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main)，mute 来自 `mute.zip`，解压前检查成员路径并放入新暂存目录，再核对上述布局，防止多套一层目录或覆盖旧资产。不要下载/反序列化来源不明的 pickle、checkpoint；SHA 一致只证明字节，不证明文件本身可信。

**HuBERT 是 Hugging Face/Transformers 目录，不是旧 `hubert_base.pt`。** 固定 `infer/hubert.py` 使用 `local_files_only=True`，要求 config、preprocessor 和模型字节配对，v2 使用第 12 层 768 维特征；v1 使用第 9 层加 final projection 至 256 维，不能混用。无需 fairseq legacy `.pt`，也不需要 DDSP ContentVec、DDSP config、PC vocoder 或任何角色 DDSP 权重。

创建输出父目录避免历史“保存小模型时父目录不存在”的错误：

```bash
mkdir -p "$RVC_APP/assets/weights" "$RVC_APP/assets/indices"
```

## 3. 逐资产加载关口

仅在来源可信且字节校验完成后，在 RVC 根分别导入并加载 HuBERT、RMVPE，在**本次授权短录音**上运行后续特征命令；记录设备和实际精度。`True` 是半精度请求，代码可能按硬件回退，不是中文模式。首次运行只做短段，检查日志无异常、输出非空、finite 和尺寸，再扩大到全部训练数据。

FAISS 检查在索引建好后做 `d == 768`、`is_trained`、`ntotal` 与本次建索引日志一致；这需要 FAISS 依赖和可信索引，不属于标准库 hash helper 的能力。

## 4. 绑定阶段而非一键执行

保存部署资料后转[数据与训练](training.md)。`RVC_APP/logs/$EXP` 是官方入口固定使用的实验位置，不是随便改 cwd 就能指定的目录。每个新角色/语言/数据版本用新实验，主唱/和声短段转换各自新输出。

恢复前按[run-input 护栏](repair.md)校验源字节、实际参数、源码/配置和依赖。标准库脚本可以在控制端跑，但训练路径必须在实际 RVC 机器上生成；不能把控制端绝对 filelist 原样拿到另一台机器上使用。
