# 从一句话准备一组 ComfyUI 图片或视频任务

Agent 把用户要求整理成逐镜头清单，再顺序完成“参考图 → 独立视频片段 → 合集剪辑”。默认本地 ComfyUI；连接方式见[本地版](local.md)和[远程版](remote.md)。模型选择沿用[家族与提示词](families-and-prompts.md)、[发现与下载](model-discovery.md)，具体工作流按[Toolkit 关联规则](toolkit.md)获取固定版本。

`prepare_graph.py` **只生成可提交的 JSON 文件**，不连接服务、不下载模型、不生成图片或视频，也不进行视觉检查。“批量”由 Agent 按镜头清单顺序调度，不能把准备完成说成视频生成成功。

## 1. 为每个镜头准备独立输入

每项记录 `shot_id`、角色与服装、构图、图像提示词、动作提示词、用途、seed 和输出前缀。相同角色可共用身份设定；不同镜头分别保存参数和结果，首帧文件不能互相串用。

- 有指定角色就围绕该角色生成；没有现成图片时调用本 Skill 制作。人物一致性依赖实际提示词、模型/LoRA 和参考输入，不能凭“沿用上一张”几个字保证。
- 首先准备一张、`batch_size=1`。检查绑定图和 `/object_info` 后再提交，首张技术检查完成后才展开其余任务。需要画面验收时另做视觉检查；用户禁止视觉检查则保留 `visual_review=pending`，不要打开图片或调用视觉模型。
- 每次候选使用独立项目目录、`client_id` 和输出前缀。前缀可用 `showcase/run-<uuid>/shot-001/reference`；重做保留旧记录并建立新版本。
- seed 使用 JSON 整数，`0` 是有效值；不要经过 JavaScript 浮点转换而损坏较大的种子。

## 2. 离线绑定 API 图

设置 `SKILL_DIR` 为本 Skill 目录，`PROJECT_DIR` 为本次项目目录；输入图由 Toolkit 解析器获取。以下命令仅准备文件：

```bash
python3 "$SKILL_DIR/scripts/prepare_graph.py" \
  --template "$PROJECT_DIR/workflows/character.api.template.json" \
  --values "$PROJECT_DIR/shots/001/reference.values.json" \
  --output "$PROJECT_DIR/shots/001/reference.api.json" \
  --output-node 12 \
  --manifest "$PROJECT_DIR/shots/001/reference.prepared.json"
```

先建立输出父目录。文件已经存在就停止；恢复应使用已有图及台账，修改参数则选择新的版本目录，不能覆盖已提交任务。

模板中的完整值 `"{{seed}}"` 会被替换为 JSON 整数；`"{{cfg}}"` 可替换为数值。内嵌形式如 `"Scene: {{prompt}}"` 只接受字符串，脚本解析 JSON 后替换，不把角色名或提示词拼进 shell 命令。参数只展开一次，不执行其中的表达式。

**SDXL 两次采样示例**：下列文件名仅演示结构，必须替换为该实例模型枚举里已经核验的相对名称。此图包含四个 LoRA 加载器；不需要的 LoRA 应先在经过核验的图副本中去掉并重连，不能填空字符串或随便拿其他模型顶替。`strength_model=0` 但 `strength_clip≠0` 的节点仍然有效。

```json
{
  "seed": 0,
  "positive_prompt": "1girl, adult woman, solo, cowboy shot, consistent outfit, clean silhouette, detailed anime illustration",
  "negative_prompt": "low quality, extra fingers, extra limbs, text, watermark",
  "output_prefix": "showcase/run-001/shot-001/reference",
  "node_23_model_name": "approved-upscaler.pth",
  "node_25_ckpt_name": "approved-sdxl.safetensors",
  "node_27_lora_name": "approved-character.safetensors",
  "node_34_vae_name": "approved-sdxl-vae.safetensors",
  "node_66_lora_name": "approved-style-a.safetensors",
  "node_68_lora_name": "approved-style-b.safetensors",
  "node_69_lora_name": "approved-style-c.safetensors"
}
```

用 Anima 时，改用与其实际节点和模型家族匹配的 API 图及参数文件；不要把上述 SDXL 图中的模型名称直接换成 Anima。

**H3 动态立绘示例**：首帧必须先由 ComfyUI 生图任务成功产出并保存哈希，再上传/放入目标实例的 `input` 目录。`first_frame` 使用服务识别的相对名称；完整图来自 Toolkit 的 `h3-i2v-live-portrait`，目标输出节点为 `145`（`VHS_VideoCombine`）。

```json
{
  "diffusion_model": "approved-h3-fl2va.safetensors",
  "text_encoder": "approved-h3-text-encoder.safetensors",
  "video_vae": "approved-h3-video-vae.safetensors",
  "audio_vae": "approved-h3-audio-vae.safetensors",
  "first_frame": "showcase/run-001/shot-001-reference.png",
  "prompt": "Picture 1 defines the character, outfit and framing. She breathes gently and blinks naturally. Her hair moves slightly in the breeze. Keep the camera stable and preserve her facial features. Soft ambient wind, no dialogue.",
  "width": 864,
  "height": 1344,
  "length": 243,
  "seed": 0,
  "output_prefix": "showcase/run-001/shot-001/video",
  "rife_model": "approved-rife-model.pth"
}
```

使用同一条绑定命令，替换输入/输出文件并设 `--output-node 145`。此示例参数来自已收录的链路记录，公共图适配未经本轮推理验证；实际可用模型名、尺寸、长度和插件版本仍需核验。原生 24 fps 的 `length` 与 RIFE 后 60 fps 的输出帧数不同。

绑定器拒绝缺失/多余参数、遗留占位、非法边、环、与目标输出无关的节点、空模型名、绝对模型路径、路径穿越和错误 seed 类型。它支持 `SaveImage`、`SaveVideo`、`VHS_VideoCombine` 及部分原生动画保存节点。直接数组输入按 ComfyUI 的 `[node_id, output_slot]` 连线解释；需要数组常量的特殊节点应使用专门的已核验适配器。

这只是离线结构检查：脚本不能证明节点已安装、输出槽数量/类型正确、模型存在、尺寸符合某个模型、提示词保留角色身份，或推理一定成功。

## 3. 在线核验后只提交一次

完整的端点、上传和恢复规则见[执行与恢复](execution.md)。每项按以下顺序执行，不能跳过前置结果：

1. `GET /object_info`，对照绑定图核验每个 `class_type`、required 输入、输出槽数量及类型、枚举值、数值范围。使用图中已经填好的精确模型名，核对家族与文件哈希，记录节点版本；缺项先解决，不能靠 POST 试错。
2. 需要输入图时 `POST /upload/image`，记录返回的 `name/subfolder/type`，把服务端实际名称写入本镜头 values 后重新准备**尚未提交**的新图。保留输入图哈希；客户端绝对路径不能写进 `LoadImage.image`。
3. 生成新的 UUID 作为 `client_id`；在发送前持久化台账、图的 SHA-256、输出节点和前缀。把状态先置 `unknown`，表示即将提交但尚未确认，以免进程在请求后崩溃时误认为从未发送。
4. 仅发出一次 `POST /prompt`，JSON 为 `{"prompt": API_GRAPH, "client_id": RUN_UUID}`。HTTP 请求必须有超时，**不得配置自动重试 POST**。Toolkit 的通用 runner 可能重试 POST，不能因此视为幂等提交器。
5. 响应出现 `error` 或非空 `node_errors`，优先记录 `failed`；仅在无错误且收到 `prompt_id` 时立刻落盘并置 `submitted`。只收到 HTTP 200 不算提交成功。
6. 有 `prompt_id` 后，只恢复查询同一 ID 的 `/history/{prompt_id}` 和 `/queue`，不再 POST 原任务。有限时长、退避轮询；读请求可以重试，提交请求不可以。

提交超时、断线、HTTP 5xx 或响应解析失败且无法确认 ID 时保留 `unknown`。使用本次 client ID、图哈希、输出前缀在队列/历史中查证；找到对应任务后绑定其 ID。没有找到不等于没有执行，禁止自动重发。

## 4. 历史错误优先，只下载本镜头目标输出

读取 history 时先检查 `status.status_str`、`status.messages` 中的 `execution_error` / `execution_interrupted` 等终止信息，再检查完成状态和输出。即使已经有某些输出，整体失败也不能当成功。空 history 或队列消失不能单独证明成功。

- 图像只取 `history[prompt_id].outputs[output_node].images`。
- 视频只取同一目标节点实际返回的 `gifs` 或 `videos`；`VHS_VideoCombine` 常将 MP4 放在 `gifs` 下，不能根据键名误判成 GIF，也不能只支持 `SaveVideo`。
- 按该记录的 `filename/subfolder/type` 构造 URL 编码后的 `/view` 请求。不能从整个输出目录找“最新文件”，也不能拿缩略图、别的镜头或中间 `PreviewImage` 当结果。
- 下载原始字节到项目内固定、独占的 `.part` 文件；不要把服务端文件名直接用作任意本地路径。核验内容类型、非空大小、格式及完整性，再原子改名，计算 SHA-256。保留完整原图，剪辑副本另存。
- 静态文件检查不等于画面验收。用户只允许文件检查时，不渲染、不播放、不调用视觉模型，并明确 `visual_review=pending`。

## 5. 顺序批量与台账

Agent 对每个 `shot_id` 顺序运行上述流程；同一镜头的参考图成功后再准备其 H3 图。失败项单独停下并记录原因，已完成项保持不变。需要并发时由明确的显存/服务容量方案另行调度，默认不把整批任务同时塞进队列。

`--manifest` 生成的 sidecar 是**准备记录**，只含初始状态和图哈希；不会自动监控任务。Agent 后续在项目内维护台账，至少包含：

```json
{
  "shot_id": "001",
  "stage": "reference",
  "state": "prepared",
  "graph_sha256": null,
  "output_node": "12",
  "client_id": null,
  "prompt_id": null,
  "output_prefix": "showcase/run-001/shot-001/reference",
  "inputs": [],
  "outputs": [],
  "error": null,
  "visual_review": "pending"
}
```

`prepared` 表示图已准备，`submitted` 表示收到 ID，`succeeded` 表示 history 成功且目标原始文件技术检查通过，`failed` 表示有明确失败证据，`unknown` 表示缺少确认；等待执行也可细分为 `running`。视觉结果单独使用 `pending/accepted/rejected`，不能与运行状态互相替代。

各输出记录相对项目路径、SHA-256、实际尺寸/时长、对应输入哈希。只有片段齐全且顺序、比例、时长和音轨与配方一致时才进入合集剪辑；不要用空白片段或旧成片填补失败而声称新生成完成。
