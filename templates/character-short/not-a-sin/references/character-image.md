# 自动准备角色参考图

没有现成角色图时，让 Agent 先生成一张，再进入视频步骤。这里抽取了已有 cowboy shot 工作流的通用方法，未附带私人工作流、固定角色或特定 LoRA。

## 先选入口

| 当前条件 | 下一步 |
|---|---|
| 已有可用 ComfyUI | 优先复用用户已授权的角色生图工作流，按下文修改和验收 |
| 想在本地生图，但尚未配置 | 按[本地 ComfyUI](../../../../docs/comfyui-local.md)准备运行环境，再用 [ComfyUI 参考图 Skill](../../../../skills/comfyui-reference-images/SKILL.md)补齐图像模型和工作流 |
| 已配置其他生图入口 | 可选 [GPT Image 2 high](../../../../skills/gpt-image2-reference-images/SKILL.md)或 [NovelAI](../../../../skills/novelai-reference-images/SKILL.md)，复用相同画面要求 |
| 已有满意图片 | 直接提供图片，完成第 4 步验收；无须重复生图 |

这些选择只解决角色图片。视频仍需要可运行的 [H3 后端](../../../../docs/local-h3.md)；上传图片或调用在线生图工具不会替代视频推理环境。

## 1. 定义这张图

确定角色身份、固定服装、画风、比例和必须露出的部位。**Cowboy shot 通常取头部到大腿的景别**：比胸像多保留身体与服装信息，头顶留白，身体和双手尽量完整。它不是全身图；视频需要明确鞋子、腿部或背面设计时，另补全身或侧背参考。

已有人物参考时先看图，列出发型、配色、服装等身份锚点。只有角色名称、却没有可核验外观或可用角色模型时，先查找或补齐参考；不把任意相似人物当成目标角色。

可按所选模型的提示词格式改写这个画面要求：

```text
One character, {{CHARACTER_DESCRIPTION}}, wearing {{FIXED_OUTFIT}}.
Cowboy shot, framed from the top of the head to mid-thigh, with headroom.
Neutral standing pose, unobstructed face, hands visible within the frame.
Plain uncluttered background, {{VISUAL_STYLE}}, clear character and clothing details.
One complete image; no extra characters, collage, subtitles, labels or watermark.
```

提交前填完占位符。根据角色实际动作调整手势，不同时堆叠 `close-up`、`full body` 和 `cowboy shot` 等互相冲突的景别。

## 2. 复用有效节点链

先按 [ComfyUI 参考图 Skill](../../../../skills/comfyui-reference-images/SKILL.md)读取 API 工作流，沿最终 `SaveImage` 反查有效分支。画布里出现过的节点不等于本次会执行；跳过、断开的支路不计入实际链路。

| 已有工作流类型 | 可复用的结构 | 应修改什么 |
|---|---|---|
| SDXL 类 | checkpoint → 可选 CLIP 层设置与 LoRA → 正负文本编码；空 latent → sampler → VAE 解码 → 保存图片 | 目标角色/服装/构图提示词、对应家族的 LoRA、输出尺寸和 seed |
| Anima 类 | 独立扩散模型、文本编码器与 VAE；可选 rgthree LoRA；文本编码 → 空 latent 与 sampler → VAE 解码 → 保存图片 | 目标人物描述、兼容的 LoRA、景别与输出尺寸；相机节点的输出必须确实进入文本编码 |

所参考的 Anima 工作流还包含 `CameraAngleNode` / `CameraExtraConfigNode`，用于组织机位描述；它们不是身份控制或视频运动控制。SDXL 工作流另有 ControlNet、放大及二次采样支路，可在基础图通过后按需启用，不必为一张角色参考先跑完整放大链。

模型、文本编码器、VAE 和 LoRA 按家族匹配，不把旧角色 LoRA 留在有效支路里。缺少模型时，按 Skill 的[模型发现规则](../../../../skills/comfyui-reference-images/references/model-discovery.md)去 Civitai 或 Hugging Face 查找、核验和下载；不按相似文件名猜兼容性，不把私人文件名写成模板依赖。

如果选择参考图编辑，必须存在可用的图像条件路径；只给纯文生图工作流传一个文件路径，不会自动保持原图身份。已有工作流不具备该能力时，选择已配置且支持它的入口，或用经核验的角色模型重新生成并验收。

## 3. 先生成一张，再决定是否重做

复用该工作流已知可用的采样设置，不把另一模型的尺寸、步数或 CFG 当通用默认。记录真实模型版本、有效 LoRA、提示词、seed、输入图哈希与 `prompt_id`；等待任务完成后取得原始图片。超时先查队列、历史和已有输出，不盲目重复提交。

## 4. 验收后交给视频流程

打开图片，确认只有目标人物、身份与服装正确，头和脸未裁断，手臂无明显异常，目标景别合适，背景不干扰人物。明显不合格时只改问题项重试；没有看图能力则标记待验收。

将合格图及生成记录保存在用户工作项目，作为该次视频的角色身份输入。图像提示词中的景别只控制参考图，成片动作、镜头和人物可见范围仍由视频驱动与 H3 生成结果决定。
