# Heartache · 一点一滴刺痛我的心

将角色参考图与动作驱动接入 MiniMax H3，在本机完成真latent续接和配乐短片。把这个目录交给支持工具调用的Agent，读 [SKILL.md](SKILL.md) 即可开始；命令也可手动执行。

一句话示例：**“用我提供的角色图，按Heartache模板做视频，先检查这台电脑能否运行。”** 若只有角色名字，按[角色输入](references/character-input.md)查找官方立绘；用户传图则直接使用。

## 包里有什么

- 首段、续接的 API与ComfyUI编辑器工作流；公开Core双路latent保存/读取和MotionContext连接。
- 驱动、配乐、历史示例图的固定来源、大小、SHA及获取脚本；默认轻量ZIP不含图片、音频、视频或模型权重，素材按需获取。
- 固定Core/节点/模型/Python依赖、兼容补丁、安装计划与只读预检。
- 用户图片入口、官方角色立绘查找方法与图片URL下载入口。
- 按实际容量分段、逐段驱动切片、显式提交、断点恢复、发布帧检查、累计拼接和连续配乐。
- 离线测试、来源与许可、历史复现说明。无需作者的个人Skill或私有服务器。

模型权重不内嵌。生成环境为Linux x86_64、CPython3.10和NVIDIA/CUDA；macOS可做素材准备与后处理，不能据此认定支持该H3模型的原生推理。显存/RAM容量要现场确认，不提供未经实测的显卡档位保证。

## 配套资源

- [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)：本模板的运行图不在本目录内维护，从这里按 `references/workflow.lock.json` 固定的版本取用；H3 环境的版本参考记录在它的 [`environments/h3/`](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/README.md)，需要去背景时用它 [`workflows/images/rmbg-2-alpha/`](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/workflows/images/rmbg-2-alpha/) 的可选工作流。
- [Shenrui-Ma/video-regen-assets](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets)：本模板的驱动视频、配乐、参考图与历史剪辑片段都放在这里，按固定 revision 分发并按 SHA-256 校验；`scripts/distribution/fetch_assets.py` 会按 `assets/runtime-assets.json` 的记录取用。模板目录不再自带这些媒体。

## 1. 准备环境与素材

全部命令从本目录运行。默认用用户已有的 ComfyUI 和模型；只有缺依赖或推理报错需要排查版本时，才查[环境参考记录](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/README.md)，按需取用其中一段。确实要另建一套时用不存在的目标目录，绝不覆盖共享环境。模型已齐全且可用时直接复用，不重复提醒下载或空间占用；仅在确认缺失后，下载前告知缺失模型、需下载的数据量和预计新增磁盘占用，只计算缺失项。检查失败不能当作模型缺失，详见[下载提醒规则](SKILL.md#下载提醒规则)。

```bash
# 只输出安装计划，审核后再在合适的Linux机器执行
python3 <toolkit>/environments/h3/scripts/install.py --target ./h3-local > install-heartache.sh

# 获取运行所需的固定驱动和配乐（校验后原子落盘）
python3 scripts/distribution/fetch_assets.py
python3 scripts/distribution/fetch_assets.py --check

# 静态图检查，不连接服务器、不采样
python3 scripts/runtime/heartache.py smoke

# 对已经启动的本机服务只读检查；模型SHA扫描需要读取完整权重
python3 <toolkit>/environments/h3/scripts/preflight.py \
  --comfy-root ./h3-local/ComfyUI \
  --python-site ./h3-local/.venv/lib/python3.10/site-packages \
  --url http://127.0.0.1:8188 --verify-model-hashes
```

安装计划不会自动下载模型或启动服务，后续命令和显存检查见安装说明。预检不通过时按具体报告处理；不能用预检HTTP成功替代GPU校准。

## 2. 绑定自己的角色

已有图片直接传给视频入口也可以。需要统一PNG和来源记录时：

```bash
python3 scripts/character/prepare_character.py \
  --image ./my-character.png --out-dir ./character-input \
  --rights-note "本人提供并授权本次使用"
```

用户未传参考图时，Agent按角色全名和作品查找官方角色立绘，核对图片对应的角色与来源，再下载使用。找不到可靠来源或角色名称有歧义时，只询问缺少的信息，不替换成默认人物。

角色输入只涉及用户图片或官方立绘的获取、必要的格式转换和来源记录；不需要安装任何参考图生图工作流。

若希望只借用人物，不把原参考图场景带入视频，按[去背景指南](references/background-removal.md)使用可选RMBG流程，再将人物alpha图合成白底RGB。保留原图、mask及输入SHA。透明PNG直接丢弃alpha会重新暴露隐藏的背景颜色，不能当作已去背景。

## 3. 按硬件准备计划

固定画布1344×768、24fps、20步、res_multistep/simple。把同配置测得的最大采样容量写入`CAPACITY`，不要按显卡名称猜，也不要直接照搬示例值。

```bash
# 示例107来自既有实测，仅说明参数填法，不是任意显卡的推荐值
CAPACITY=107
python3 scripts/runtime/heartache.py prepare \
  --character-image ./character-input/character.png \
  --character-description "按我的参考图保持角色身份与服装" \
  --max-sample-frames "$CAPACITY" \
  --work-dir ./work/heartache-01

# 不带--execute只显示计划，不提交
python3 scripts/runtime/heartache.py run --work-dir ./work/heartache-01
```

结果包含`run.json`、每段驱动和API/editor图。需要自定义驱动/配乐时用`--driver`/`--music`；驱动须与该模板24fps、1344×768及计划长度匹配，正式音轨须覆盖发布总时长。

初次上机没有可靠容量基准时，先保守估计可加载后的短段容量，并在下一步只跑首段和一次续接。采样帧使用17k+5网格，后段要计入22帧context。增加段数不会降低模型最低加载内存。

## 4. 校准、继续与恢复

以下命令会真实占用GPU。只有在用户同意生成、服务预检通过并确认资源可用后执行。先按[媒体预检与恢复](references/media-preflight.md)验证实际FFmpeg的AAC编码和拼接能力，避免采样成功后才在配乐阶段失败。

```bash
# 用户只要看第一段时，用--until-segment 1；不要额外提交续段
python3 scripts/runtime/heartache.py run \
  --work-dir ./work/heartache-01 --comfy-root ./h3-local/ComfyUI \
  --host http://127.0.0.1:8188 --until-segment 1 --execute

# 已获准做首段和一次真续接校准时；成功后保留结果
python3 scripts/runtime/heartache.py run \
  --work-dir ./work/heartache-01 --comfy-root ./h3-local/ComfyUI \
  --host http://127.0.0.1:8188 --until-segment 2 --execute

# 同一计划续跑剩余段，不重采已完成段
python3 scripts/runtime/heartache.py run \
  --work-dir ./work/heartache-01 --comfy-root ./h3-local/ComfyUI \
  --host http://127.0.0.1:8188 --execute
```

本机runner与ComfyUI共享`--comfy-root`文件系统。非本机服务须提供一致的文件访问方式并另外验证；本模板不自带SSH控制器。

- 中断或超时：保留工作目录，先读该段`job/state.json`及原prompt的history，再运行同一命令恢复。提交结果不明或原任务失败时不会自动重新采样。
- 想停后续段：在工作目录写入名为`STOP`的文件。它不等于取消服务中正在执行的prompt；共享服务需先确认prompt归属。
- 采样成功、解码失败：保留官方两路latent，按[当前生成与恢复规则](references/generation.md)核验后做无Sampler解码。不要删账本强制重采。
- 只有配乐或拼接失败：保留段目录的`verification.json`、两路latent和`published.mp4`，修复FFmpeg后按[后处理恢复](references/media-preflight.md)处理同一计划，不删除提交账本。
- OOM：区分模型加载与采样/解码峰值，记录失败位置。调整容量需新版本计划，不能偷偷修改已运行的前驱或降分辨率/步数。

## 5. 拼接与验收

续段已经按图裁掉context，累计拼接只连接发布画面，不再次删22帧。配乐从完整时间线零点连续铺设，尾部半秒淡出；不能把每段重置过的音乐直接拼起来。用户要求“第三段连前两段”时交付第一至第三段累计版。

产物和验收记录位于工作目录，CLI报告具体路径。必须有真实history success、输入/图/latent/视频SHA、连续发布区间、实际帧数、时长、音视频流和完整解码结果。人物一致、动作与接缝视觉效果另由用户确认。

[本版修订](references/changelog.md)列出修改；[首段实跑记录](references/first-segment-validation.json)保存真实输出的技术证据。[验收范围](references/validation.md)说明本次封装测试做到了哪一步。干净目录离线测试不等于在另一台GPU完成新角色全片。

## 测试与分发

离线辅助环境只需Python3.10+、Pillow11.3.0及FFmpeg/ffprobe；不要把完整H3/CUDA运行库装进这套轻量测试环境。

```bash
python3 -m venv .test-venv
.test-venv/bin/python -m pip install Pillow==11.3.0
.test-venv/bin/python -B -m unittest discover -s tests -v
.test-venv/bin/python -B scripts/runtime/heartache.py smoke

# 轻量分享包：含代码、工作流、说明和清单；全部媒体按需获取
python3 scripts/distribution/package_skill.py --output ../heartache-skill-portable.zip
python3 scripts/distribution/package_skill.py --verify ../heartache-skill-portable.zip

# 可选媒体包：先按assets/README.md显式获取所需历史素材；仍不包含模型权重
python3 scripts/distribution/package_skill.py --full --output ../heartache-skill-with-media.zip
```

将ZIP解压到名为`bit-by-bit-heartache`的新目录，以该目录的`SKILL.md`为入口。素材/模型许可见[LICENSES.md](LICENSES.md)，原版来源见[sources.md](sources.md)。历史四段成片重剪仍保留`render_default.py`，但它不会生成新角色。
