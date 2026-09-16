---
name: swimsuit-live-portraits
description: 一句话制作泳装动态立绘视频合集：用 ComfyUI 生成指定角色的首帧，逐张用本地 MiniMax H3 I2V 生成有自然声的片段，再按 8 段约一分钟的真实节奏剪辑；支持换角色、动作、场景和 BGM，包含任务恢复与原声混音。
version: 0.1.0
author: Shenrui Ma（四倍体果蝇）
license: "See LICENSES.md for component terms"
platforms: [linux, macos]
---

# 泳装动态立绘视频集

按下面顺序完成首帧、动态片段和成片。本子模板默认 8 镜头、保留自然声；其他环境和恢复规则继承[角色视频合集](../video-collection/SKILL.md)的环境、队列与交付流程，后期调用[角色展示剪辑](../../../skills/character-showcase-editing/SKILL.md)。当前模板所在目录至仓库根为 `../../..`。

## 1. 把一句话落成项目

将 [request.example.json](examples/request.example.json) 复制为用户项目的请求记录。记录角色、固定外观、场景、图像后端、BGM 路径和输出目录；将角色身份与每个镜头分别保存，避免同一角色在不同镜头变脸或换装。

- 用户指定一个角色：替换全部 8 个角色槽；多个角色：按用户顺序分配，没有顺序时均匀分配并记录。
- 用户已经提供首帧：按镜头绑定，补生成缺少的张数。只提供身份图：据此准备各镜头首帧，不能把一张立绘冒充 8 个不同场景。
- 未给角色：复用用户当前项目角色；没有项目身份时询问想使用的角色；用户选择原创时再设计统一的成年角色外观。
- 默认采用 [8 段计划](examples/eight-shot-plan.json)的动作与剪辑范围，约 62.15 秒。角色不具备机械配件时，第 4 段改成普通发饰随风运动，保留害羞和卡通表情的时间顺序。
- 未给 BGM：保留 H3 自然声，不自动取用示例案例歌曲。只要求重剪现成片段时跳过生成，交付明确标为重剪。

先检查本地 ComfyUI、H3 图、图像模型、Python + Pillow 与 FFmpeg。配置缺口能通过现有模型盘点、官方模型文件查找和工作流解析补齐的，直接处理；缺少用户专有资产时明确缺项。不要每个镜头重复问同样的问题。

项目至少保存 `request.json`、`character.json`、`shots.json`、`images/`、`clips/`、`records/`、`edit.json`、`output/`。路径均相对该项目；原素材只读，新版本另存。

## 2. 在 ComfyUI 生成首帧

执行 [ComfyUI 参考图 Skill](../../../skills/comfyui-reference-images/SKILL.md)，并读[本模板生成说明](references/generation.md)。默认本地；用户指定服务器时再读该 Skill 的 `references/remote.md`。

1. 匹配图像模型家族和角色 LoRA。现有模型优先；缺模型时沿共同 Skill 的 Civitai/Hugging Face 发现流程，核对具体文件、家族、来源和许可。不能用名称相近的异家族模型代替。
2. 从 [first-frame.template.txt](prompts/first-frame.template.txt) 和镜头表构造提示词。同一角色复用身份描述、LoRA 版本与服装描述；姿态、景别和环境变化按镜头记录。
3. 解析固定 Toolkit 版本中的图像工作流，例如 `sdxl-two-pass-cowboy-shot`，按其参数定义绑定实际模型、提示词、种子与尺寸。需要坐姿或全身构图时修改提示词和画幅，不被工作流名称限制。详细历史生成参数见生成说明；不是所有图像家族都照搬同一组数值。
4. 先生成一张并记录 `prompt_id`；通过后完成其余首帧。保存原输出、PNG 去元数据的分享副本、每张 SHA-256、模型/工作流版本和角色槽。首帧中的角色必须就是视频目标角色，不能依赖 H3 提示词覆盖错误身份。
5. 给每个首帧固定 `shot_id` 和 `first_frame`。换图后只使该镜头及其后期缓存失效，保留其他成功项。

通过条件：8 个首帧槽均绑定真实文件；每张图有生成记录或用户提供记录，且身份和姿态检查的状态明确。仅文件检查时记 `visual_review: not_performed`，不能写画面已通过。

## 3. 每张首帧生成一段 H3 视频

按[生成说明](references/generation.md)从固定 Toolkit 解析 `h3-i2v-live-portrait`。使用 `MiniMaxH3ImageToVideo.first_frame`，不是 Ref2VA 的人物外观引用，也不跨镜头续接 latent。

1. 首帧上传至执行 ComfyUI 的 `/upload/image`；把响应里的实际文件名及子目录绑定到对应 `LoadImage`，不能直接填客户机绝对路径。
2. 按 [h3.template.txt](prompts/h3.template.txt)填入角色、首帧事实和镜头动作。保留 `<Picture 1>`、`[Shot 1]` 及声音段落；一张首帧只对应一段连续镜头。
3. 默认 864×1344，20 步，`res_multistep` / `simple`。按镜头表设置 `length`；本图包含 RIFE 24→60fps。长度不是容器秒数，也不直接等于最终发布帧数。不要对结果裁到整数 10 秒或 15 秒。
4. 保存渲染后的 API JSON、SHA-256、模型版本、seed、预期输出节点，然后 `POST /prompt` 一次。收到 ID 后立即落盘；以该 ID 查询 `/history/{prompt_id}`，下载指定输出节点的文件，先保存 `.part`，完整后再改正式名。
5. 断连先查询已知 ID 的 history/queue，不重复提交。提交响应丢失且无法确定 ID 时停止该项自动重试，记录 `submission_unknown`；成功片段不重跑。失败项与旧版本都不能因文件名前缀相似而冒充本次输出。
6. 核对音视频流、实际帧数、帧率、SAR 和时长。保留原音轨；不存在自然声时标记事实并补等长静音供剪辑，不能宣称模型生成了声音。转交后期时使用真实媒体时长及锁定文件 SHA。

原案例还做了 RTX VSR 3× ULTRA。当前默认直接使用 H3/RIFE 片段，超分可按用户设备与需求追加。做超分时要求帧数、帧率和音轨一致，记录独立阶段；不要把 3× 超分等同于补帧，也不要擅自用重复帧代替 RIFE。

## 4. 剪成竖屏合集

通过[公共剪辑 Skill](../../../skills/character-showcase-editing/SKILL.md)执行[剪辑规则](references/editing.md)。复制可直接使用的 [edit.json](examples/edit.json) 到用户项目，绑定 8 个视频路径并更新实际源时长；有配乐时使用 [edit-with-bgm.json](examples/edit-with-bgm.json)。先验证数据和计算时间线，再渲染。

默认：1080×1920、60fps、主体等比居中、同一时刻画面作模糊背景；开头 0.5 秒从运动中的模糊画面过渡到清晰；所有相邻片段 0.2 秒交叉溶解；原声同步裁切/变速/交叉淡化；有用户 BGM 时降低 12dB 混入；最后 1 秒画面与全部音频同步淡出。

别把开头改为静止首帧，也别把动态视频套上图片缩放曲线。默认不补时、不循环视频；更改镜头数量或范围后重新算总长。新图生成的动作时机可能变化，剪辑范围应以当次记录为准，历史时间点只是可执行的起点。

## 5. 交付与检查

交付成片、8 个首帧与原始动态片段、提示词、模型/图版本、种子、任务 ID、SHA-256 和最终时间线。报告完成/失败/未检查镜头，不把“代码可读、图结构可解析”写成“新角色生成成功”。

用户只要求整理或文件检查时，仅解析 JSON、检查链接/占位符/文件存在性、校验哈希与时间线算术；不启动 ComfyUI、RIFE、RTX VSR、FFmpeg 渲染或视觉检查。真正生成任务的验收按父模板执行；禁止视觉检查时保留该状态，交付供用户确认。
