# Agent 部署与按硬件分段

目标：测试者的 Agent 读取模板后，检查并安装环境、准备输入、生成视频和导出。原作者的四段参数只供历史对照；新任务不要求四段。

当前已提供独立运行入口、完整公开依赖锁与工作流。环境的版本参考见[环境参考记录](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/README.md)（默认先复用用户已有环境），当前依赖以[环境依赖锁](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/dependencies.lock.json)为准；[node-sources.md](node-sources.md)保留历史来源，不能当成当前安装清单。封装验收范围见[validation.md](validation.md)。

## 1. 检查并部署

1. 检查操作系统、GPU型号、可用显存、驱动、RAM和磁盘。已有服务时只读检查，避免覆盖正在使用的环境。
2. 能复用用户已有环境就直接推理；确需另建时，在使用者授权的新目录按环境参考记录创建Linux x86_64、Python3.10、CUDA环境，执行锁定wheel安装、pip check和两个hash-gated补丁，不安装浮动最新版。
3. 从当前锁的不可变公开URL取得模型，核对许可、放置位置、大小与SHA。当前图使用Core双路Save/Load和公开MotionContext，不依赖历史私有Save/Load/Trim包。
4. 启动本次独立实例并做preflight，确认首段和续段schema；在得到生成授权后，用短段和一次真续接校准完整链路与容量。

安装、模型下载与推理在使用者授权范围内执行。支持范围与尚未实机验证内容必须如实告知；不能把离线准备通过当作Windows、macOS或任意显存容量的推理支持。

## 2. 从显存与实测容量预分配

先保持用户要求的画幅、精度与采样质量。找同模型／节点版本、分辨率、参考输入数量、精度和 offload 配置的容量记录；据可用显存预留余量，给出初步单段采样帧上限。没有对应记录时标为预估，通过短片、文本与参考编码、两路 VAE 解码和一次真实续接校准。采样容量取所有阶段均能通过的保守上限。

不能仅凭 GPU 名称或总显存承诺“8GB 固定几段”。参考数量、attention 实现、RAM/offload 及显存碎片都会影响峰值。模型加载本身无法完成时，增加段数无效；向使用者说明阻塞，质量变化或改用其他设备由使用者决定。

Agent 取得采样容量后，可用下列工具生成分段账本。`MAX_SAMPLE_FRAMES` 是 Agent 基于上述检查选出的上限，包含续接 context，不是输出发布长度；不是让使用者自行猜测该数值。

```bash
python3 "$TEMPLATE_DIR/scripts/plan_segments.py" \
  --frames "$TARGET_FRAMES" --max-sample-frames "$MAX_SAMPLE_FRAMES"
```

stdout 为 JSON，由 Agent 保存到新项目。硬件信息可能含 GPU UUID，公开运行报告前应脱敏。工具会读取本机 NVIDIA 信息（若可用），按 `17k+5` 网格和默认22帧 context 计算段数、采样长度、目标时间线、裁切和前驱关系。它不自动探测推理容量、不安装、不提交 GPU 任务；输出始终保留 `inference_verified=false`。尚未收集跨显卡实测容量表，所以当前容量选择与校准仍由 Agent 完成。

采样上限降低时段数增加；上限提高时可减少。所有发布区间合计必须等于当前目标帧数，不能固定为历史发布帧和或历史 PR 时长。音频 context 参数仍按节点实现核对；该历史实现固定24fps换算，不能任意改 FPS 后照抄。

## 3. 将计划用于生成

- 计划中的 `timeline_start/end` 是目标发布坐标，不是已经校准的参考视频切点。按实际源 FPS 与新时间线制作参考，另记驱动区间；参考重叠不要与输出 Trim 混用。
- 更新每段提示词的时长和动作时间戳。首段生成后保存 canonical AV latent，后段按 `predecessor` 串行加载；每段图绑定自己的参考、采样帧数和发布区间。
- 原生 Motion Context 取前段物理尾端。计划记录的未发布尾部、首段最短可用 context、实际节点返回的 trim 均要在真实续接试验中核对；数学计划不能证明接缝连续。
- 每段校验后将图、输入哈希、seed、Prompt ID、latent 哈希及输出绑定到同一运行记录。断线先查原任务，不重复提交。
- 用新计划的任意段数与实际发布片段生成后期时间线，重新检查动作边界和音乐同步。不将新结果送进只接受历史素材哈希的 `render_default.py`。

## 4. 完成条件

依赖来源完整公开、干净环境按文档安装成功、首段与真实续接均完成、按硬件计划生成完整目标视频、技术检查及用户要求的画面／声音验收通过，才将模板标为对应配置已验证。历史图恢复、离线计划测试和旧素材重剪不能代替这些步骤。
