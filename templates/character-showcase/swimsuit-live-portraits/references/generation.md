# 首帧与动态生成

## 首帧来源和可复用参数

历史案例的多张 PNG 含有 ComfyUI `prompt` / `workflow` 文本元数据，读取这些 JSON 即可确认生成链，无需观看图片。已核对的 4 张首帧包含以下结构：

| 阶段 | 历史参数 / 节点 |
|---|---|
| 图像家族 | SDXL / Illustrious，`CheckpointLoaderSimple`、角色/画风 `LoraLoader`、SDXL VAE |
| 初始 latent | 1296×2016，batch 1 |
| 主采样 | `KSampler`，35 步，CFG 7，`euler_ancestral`，`normal`，denoise 1.0 |
| 独立细化采样分支 | 图中另存 20 步、CFG 7、同采样器/调度器、denoise 0.1；部分缺少 latent 输入，不可视为已执行的第二遍 |
| 可选人脸分支 | `FaceDetailer`：20 步、CFG 8、`euler_ancestral` / `simple`、denoise 0.2 |
| 图像处理 | `PatchModelAddDownscale`、VAE 编解码、模型放大和尺寸调整节点 |

这是归档参数，不是所有节点都必须保留的最小流程，也不是该组参数已在任何消费级显卡上验证过。回溯发现 3 个保存输出分支，其中主采样与另存的低 denoise 采样不构成同一条串联链；元数据未独立标明当前 PNG 来自哪一个保存节点。复用时从选定 `SaveImage` 回溯祖先节点，再确定有效链，不能把整张图里所有节点串成“历史实际流程”。

新项目默认按[参考图 Skill](../../../../skills/comfyui-reference-images/SKILL.md)调用固定 Toolkit 的 SDXL 两阶段工作流。先用相同身份描述生成各镜头姿态；配置允许时可采用历史 1296×2016，显存不足时按所选模型推荐尺寸生成再保比例适配。Anima 需使用自己的模型和图，不继承 SDXL LoRA/CFG 组合。保存图像原始尺寸与送入 H3 的尺寸，不能静默把非目标比例拉伸。

8 个镜头首帧可见 [shot-plan.md](shot-plan.md)。人物和场景关系应在首帧成立：坐在池边的踢水镜头应先有池边坐姿；抬手、侧身和回眸由该姿态自然延续。首帧角色与目标不一致时先修首帧，不用 H3 强行换人。

## H3 固定图

工作流 ID：`h3-i2v-live-portrait`。具体图在 [Toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit) 的 `workflows/h3/i2v-live-portrait/`；通过 Recipes 的[固定版本解析器](../../../../skills/comfyui-reference-images/references/toolkit.md)获得图和 SHA-256，按图随附参数定义填入字段。

复制父模板的 [H3 参数文件](../../video-collection/examples/h3-values.template.json)，为每镜头填入实际模型名、上传后的首帧名、完整 prompt、数值型尺寸/length/seed 与唯一输出前缀。按[父模板调用说明](../../video-collection/references/generation.md)运行 `resolve_workflow.py` 和 `prepare_graph.py --output-node 145`；这两步只下载/绑定图，不提交推理。第 6 段使用自己的 length=240，其他段按本例计划设置，不能把一份绑定值原样用于全部镜头。

```text
ComfyUI 首帧 → LoadImage → MiniMaxH3ImageToVideo.first_frame
                                      ↓ 条件 + 视频 latent + 音频 latent
                         noise + guider + sampler + scheduler
                                      ↓
                           SamplerCustomAdvanced
                           ↙                 ↘
                    VAEDecode            VAEDecodeAudio
                       ↓                       ↓
                RIFE 24 → 60fps  →  VHS_VideoCombine
```

| 项目 | 该案例参数 |
|---|---|
| H3 分辨率 | 864×1344，竖向 9:14 |
| 采样 | 20 步，`res_multistep`，`simple`，denoise 1.0 |
| 约 10 秒片段 | 多数输入 `length=243`；第 6 段历史图为 `240`，输出均记录为 607 帧 / 60fps |
| 约 15 秒片段 | 输入 `length=362`；输出记录为 905 帧 / 60fps |
| RIFE | source 24、target 60、scale 2、batch 1、FP16；模型文件按图与发布方核对 |
| 原生声音 | 音频 VAE 解码结果接入合成节点，保持与画面同步 |
| 历史超分 | RTX VSR 3× ULTRA，2592×4032，保留音轨和 60fps；新默认不强制超分 |

`length` 是节点输入，不能用 `length / 60` 推断时长。对齐、模型实现及插帧都会影响最终帧数。H3 每个镜头分别生成，没有镜头间 latent 延续。实际输出为 607/60≈10.116667 秒或 905/60≈15.083333 秒时保留完整输出，后期再取需要的范围。

历史图存在不同加速实现，包含显存优化 attention 或 SageAttention、SolAttn、EasyCache；不能只删除节点而不重接其模型边。使用固定图的已声明依赖并查询 `/object_info` 检查，缺依赖时明确阻塞项。不可将某一台机器上的速度/显存需求当作通用承诺。

## 调用和恢复约束

- 先 `/object_info`、模型列表、`/queue` 检查，再上传首帧；执行端文件名以 `/upload/image` 响应为准。
- 固定每段 `seed`，保存 API 图和输入图 SHA 后提交；`prompt_id` 与镜头一对一，不找整个 output 文件夹“最新的 mp4”。
- 下载目标输出节点对应文件，保留音轨，记录尺寸、帧率、帧数、时长和 SHA。收到任务终态成功但没有目标文件，仍算未完成。
- 换角色需要先更新首帧；换动作仅更新该镜头文本与新 seed；单纯换配乐只重跑后期。
- 本次收录只检查文件与记录，未重新执行上述推理步骤。
