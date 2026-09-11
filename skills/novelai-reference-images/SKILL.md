---
name: novelai-reference-images
description: 使用 NovelAI 官方图像 API 制作角色参考图和分镜关键帧。包含提示词组织、文生图、图生图、参考功能选择、单次提交与下载校验；适用于用户明确选择 NovelAI 的任务。
---

# NovelAI 参考图

先把需要的图片列清楚，再调用一次、检查一次。不要把“下载成功”当作“角色一致”。

## 前置条件

- 用户选择了 NovelAI，已明确本次张数、用途与可用费用；已有授权直接继续，超出范围才询问。
- 运行环境有 Python 3.10+；`NOVELAI_API_KEY` 已安全设置。只检查是否存在，不打印值，不索取账户密码。
- 已知目标比例、角色固定特征、这张图的姿态/镜头；图生图还需要可用的输入图和上传授权。
- 输出放在用户项目目录，绝不放进安装目录或公开仓库。

## 执行顺序

1. **确定图片职责。** 身份参考、风格参考、首帧、尾帧分别列出；记录必须保留和允许改变的内容。按 [提示词与验收](references/prompting.md) 写草稿。
2. **选择官方能力。** 读 [API 接入](references/api.md)：有底图且要保留构图选图生图；只需要新图选文生图；保持角色外观/风格时区分 Precise Reference 与 Vibe Transfer。不要把参考图功能当成视频生成。
3. **核对配置。** 从当前官方资料或用户已授权的官方成功请求中，核对模型 API ID、action、sampler 和配套字段。展示名不能当 API ID；资料不足就停在这里，报告缺哪个值，不能猜或换低版本。
4. **组装并预检。** 复制 [请求骨架](examples/request.template.json) 到用户项目，填完占位符。不要删掉当前模型必需字段。运行下方 dry-run；通过条件是 `dry_run_only`，它只代表本地检查通过。
5. **提交一张。** 核对费用范围后执行一次。记录请求指纹与状态，不并发、不循环刷图。超时或中断按 [恢复规则](references/api.md#失败与恢复) 处理，禁止自动再提交。
6. **验收和交付。** 打开图片检查身份、服装、姿态、裁切和跨帧连续性。合格后交付图片路径、用途、实际参数及剩余问题；不合格记录具体差异，在剩余预算内修改一项再试。

## 命令

命令中的 `SKILL_DIR` 指本 Skill 的安装目录，`PROJECT_DIR` 指用户项目；先由宿主解析成真实路径。密钥由宿主注入环境，不能写进命令参数。

```sh
python3 "$SKILL_DIR/scripts/novelai_image.py" --request "$PROJECT_DIR/request.json"
python3 "$SKILL_DIR/scripts/novelai_image.py" --request "$PROJECT_DIR/request.json" --run-dir "$PROJECT_DIR/runs/frame-001" --config-verified --execute
```

`--config-verified` 是 Agent 核实配置后的声明，不会替你查询模型。客户端只支持单张 PNG 文生图/图生图；高级参考功能的官方路径见 API 文档，不能往脚本中强塞未知字段。

**验证范围：** 已核对官方文档，客户端有离线测试；没有执行付费生成，也没有宣称任意当前模型组合已实测。来源与资料缺口见 [API 接入](references/api.md)。
