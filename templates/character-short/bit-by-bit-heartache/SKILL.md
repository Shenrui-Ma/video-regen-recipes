---
name: bit-by-bit-heartache
description: "用角色参考图在本机制作 Heartache 连续动作配乐短片."
version: 0.3.0
author: Shenrui Ma（四倍体果蝇）, Hermes Agent
license: "See LICENSES.md for component and asset terms"
platforms: [linux, macos]
metadata:
  hermes:
    tags: [video, minimax-h3, comfyui, heartache, continuation]
    related_skills: []
---

# Heartache · 一点一滴刺痛我的心

用角色图片提供身份条件、驱动视频提供动作条件，以 MiniMax H3 Ref2VA 分段采样，通过前段联合音视频 latent 真续接，按发布帧拼接并连续铺设配乐。这个目录可独立分发；不需要作者的聊天记录、个人 Skill、GPU 主机或消息机器人。

## 何时使用

用户要求“用这个角色做《一点一滴刺痛我的心》”“Heartache”或提供参考图复现同类连续动作短片时使用。新角色必须重新生成；仅用户明确要求重剪已有成片时使用历史编辑入口。

## 前提

- Agent 可用 `terminal`、`read_file`、`write_file`，必要时用 `web_search`、`vision_analyze`确认角色输入。所有脚本路径相对于本目录。
- Python、FFmpeg/ffprobe；离线准备可在 macOS/Linux 完成。固定生成环境为 Linux x86_64、Python 3.10、NVIDIA/CUDA。不能把 Mac 上的离线测试当作 H3 原生推理支持。
- 默认**复用用户已有的 ComfyUI 与模型**，不要求为了这个模板重装或对齐版本。只有在缺节点、缺模型、版本冲突或推理报错、需要判断该改成什么版本时，才查 [环境参考记录](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/README.md)，按需取用其中一段。本机 RAM/显存必须足够加载模型，并完成同配置首段与续接校准。
- [README](README.md)有完整命令。[角色输入](references/character-input.md)处理一句话、图片和公开 URL。[验收说明](references/validation.md)区分已有实跑证据与本次封装测试。

## 下载提醒规则

先检查用户实际生成环境的模型目录、配置的共享路径和可复用缓存，按依赖清单核验已有文件是否完整、版本是否匹配。仅在确认缺少所需模型时，才在下载前提醒用户缺少哪些模型、需下载多少数据及预计新增磁盘占用；只计算缺失项。模型已齐全且可用时直接复用，不重复提醒下载或空间占用。检查失败或路径不可访问时明确说明尚未核实，不能当作模型缺失。可选模型仅在本次确实使用对应功能时检查并提醒。

## 执行顺序

1. **绑定角色。** 优先用户参考图，其次当前项目已确认图。未提供图片时，按角色名字和作品查找官方角色立绘，核对身份与来源后作为参考；角色信息不足时只补问必要信息。用户已指定角色时不得替换成默认人物。保存输入 SHA、来源、描述和授权范围；得到可解码的 `character.png`。若只要人物、参考背景与驱动场景无关，按[可选去背景](references/background-removal.md)先处理；透明结果须明确合成纯色RGB，不能仅去掉alpha通道。
2. **确认依赖可用。** 先用用户现有实例推理；报错或缺少节点/模型时再定位是哪一层（缺节点 / 缺模型 / wheel 冲突 / 源码补丁），需要版本依据时查 [环境参考记录]。可选地只读核对现有实例：`python3 <toolkit>/environments/h3/scripts/preflight.py --comfy-root ... --url ... --workflow-lock references/workflow.lock.json`，这是诊断而非前置步骤。按[媒体预检](references/media-preflight.md)在实际runner环境测试AAC及后处理。既有节点未加载时区分禁用、导入失败与缺安装。正常加载已启用节点，不默认增加白名单。
3. **核验素材。** 用 `terminal` 执行 `python3 scripts/distribution/fetch_assets.py`，再执行 `python3 scripts/distribution/fetch_assets.py --check`。运行驱动是 `assets/reference/heartache-driver-577f.mp4`，不要误用历史45fps原视频。校验 SHA、帧数、尺寸、完整解码。
4. **按硬件分段。** 不照搬历史四段或一次测试的七段。固定1344×768、24fps、20步、`res_multistep/simple`；以同配置实测单段容量传入 `--max-sample-frames`。首次上机按 README 校准；容量预估不可标成实测。
5. **离线准备。** 用 `terminal` 执行 `python3 scripts/runtime/heartache.py prepare --help`，提供角色图、容量和独立输出目录。核对 `run.json`、逐段 API/editor 图、驱动切片和发布计划；此步骤不发起采样。
6. **真实运行。** 先做只读 preflight，再显式使用 `run --execute`。只要第一段时使用`--until-segment 1`，不顺带运行续段。串行运行，每次保存真实 prompt_id，等待 history success 并核验落盘原件，才进入下一段。断线先查原任务；提交回执未知时禁止自动再投。续跑使用同一个工作目录，不重建已完成段。
7. **续接和拼接。** 前段 AV latent 用 Core Separate→两路 SaveLatent 保存，下一段两路 LoadLatent→Concat→MotionContext。完整 latent 保留作前驱；只裁一次解码画面的 context。按计划拼接已发布画面，音乐从累计时间线零点连续铺设。用户要求第N段连前段交付时，交付累计拼接，不默认单发第N段。
8. **交付。** 返回实际成片、帧数/时长、素材与图 SHA、技术验证和未验内容。发送到聊天时由使用者的 Agent 显式绑定当前目标并保存回执；生成入口只写本地文件，不硬编码任何平台账号。

## 常见陷阱

- Ref2VA 的身份/视频条件不是逐帧骨骼锁定；技术通过不代表角色或动作语义逐帧一致。
- 续接的22帧视频context与音频24参数不是同一种单位；后者不能解释为“24秒”。MotionContext 的 trim 输出是 INT，必须连 ImageFromBatch 的 `batch_index`。
- 对联合 NestedTensor直接 SaveLatent 会失败；使用随包官方双路路径。已验证格式是F32，不能把无损结论推广到其他dtype。
- 采样成功后解码失败，先使用已保存 latent恢复，不重复采样。若发布视频已完整保存而配乐失败，只恢复后处理；残留不完整文件不能当成已验证成片。音轨太短时不能用 `-shortest` 截掉视频。
- OOM先判断是模型加载还是采样/解码峰值；仅减段长不能解决最低模型驻留容量不足。不擅降分辨率、步数或替换量化模型。
- `STOP`只阻止后续提交；操作共享ComfyUI的interrupt前必须确认正在运行的prompt属于本任务。工具超时先查PID、history和文件，不重复启动。
- 运行图不在本仓库维护：`references/workflow.lock.json` 固定 toolkit 的 commit 与逐文件 SHA-256，runtime 取回并校验后再绑定参数（缓存在 `workflows/_toolkit_graphs/`）。`workflows/*.editor.json` 只是可读的预览图，`node-schema.json` 用于离线校验。

## 验收

用 `terminal` 执行 `python3 -B -m unittest discover -s tests -v`及 `python3 scripts/runtime/heartache.py smoke`。离线通过只证明脚本、图、输入和后处理；新机器仍须完成首段及真续接GPU校准。最终核对连续发布区间、总帧数、24fps、1344×768、单条连续配乐、完整解码及文件SHA。没有做视觉检查时明确保留给用户确认。
