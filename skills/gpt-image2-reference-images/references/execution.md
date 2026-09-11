# 调用方式

## A. 宿主原生生图工具

读取当前工具说明，确认可附加本地图片，以及能否选择 `gpt-image-2`、`quality=high`。工具名由宿主提供，不假定存在某个固定命令。

先查看参考图，再通过工具实际支持的附件参数传入。一张图一个任务，保存实际请求参数、任务标识和工具返回的文件位置。若工具未暴露模型／质量或结果未说明，记为未知；提示词中的参数请求不能当成执行证据。需要严格 Image 2 high 时采用下方官方 API。

宿主返回图片后，用该任务明确返回的原始文件。若只缺项目中的副本，从本任务返回路径恢复；不要扫描全局缓存并选“最新的一张”。登录与认证交由宿主管理，不从其他程序的凭据文件提取令牌。

## B. 官方 Responses API

链路：**读取任务与图片 → 图片转 data URL → 提交 Responses → 提取完成的图像工具结果 → 解码原始 PNG → 写入运行记录 → 看图验收**。

顶层 `model` 是有图像工具能力的语言模型；工具内部的 `model` 才是 `gpt-image-2`。`quality=high` 是图像工具参数，与语言模型的 reasoning effort 无关。使用 `input_image` 附加图片，并要求 `image_generation` 工具调用；输出读取 `image_generation_call.result`，同时保存可用的 `revised_prompt`。[官方图像工具说明](https://developers.openai.com/api/docs/guides/tools-image-generation)

本包客户端固定访问 `https://api.openai.com/v1/responses`，从 `OPENAI_API_KEY` 环境变量读取用户自己的 API key。不会读取宿主登录令牌、切换中转服务或打印认证头。需要 Python 3.10+，无额外包。

### 1. 准备任务

在 Skill 目录以外建立项目。新建 `prompt.txt` 和 `task.json`；文件路径相对 `task.json` 所在目录解析。

```json
{
  "prompt_file": "prompt.txt",
  "size": "1536x1024",
  "references": [
    {"path": "inputs/character.png", "role": "identity"},
    {"path": "inputs/scene.jpg", "role": "scene"}
  ]
}
```

无参考图时 `references` 写 `[]`，但不适用于已经要求保持角色身份的任务。角色、场景、姿态与风格等用途要在提示词里逐项对应；本客户端一次最多 4 张参考、单文件最多 20 MiB、PNG 最多 8294400 像素，是本包的保守限制，不是官方上限。

### 2. 离线检查，再执行

先由宿主将 `SKILL_DIR`、`PROJECT_DIR` 解析为安装目录和项目目录，将 `RESPONSE_MODEL` 设置为用户可用且支持图像工具的语言模型 ID。不要将 `gpt-image-2` 填入该变量。

```bash
python3 "$SKILL_DIR/scripts/generate.py" --task "$PROJECT_DIR/task.json" --response-model "$RESPONSE_MODEL" --run-dir "$PROJECT_DIR/runs/frame-001"
```

默认只检查并创建运行计划，不联网、不要求 key。看过参考图并确认输入后，在同一命令末尾加 `--execute` 才会提交一次。已有用户授权足够时直接继续；未配置 key、模型访问或预算时只补齐相应缺项。

本客户端将 `store=false`，不依赖服务端保存后再取回。非流式请求减少误把预览图当成终图的分支；`max_tool_calls=1` 限制内置工具总调用次数，一次只接受一个完成的图像结果。[Responses 参数](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)更复杂的流式实现必须区分 partial 与 completed，不照搬“最后收到的 base64 就是终图”的做法。

### 3. 参数规则

锁定 [GPT Image 2](https://developers.openai.com/api/docs/models/gpt-image-2)，不跟随其他模型的默认值。按[官方尺寸规则](https://developers.openai.com/api/docs/guides/image-generation#earlier-gpt-image-models)：两边为 16 的倍数、最大边 ≤3840、长宽比 ≤3、像素总数 655360–8294400。客户端要求明确尺寸，不用 `auto`；默认 1536×1024。

输出固定 PNG，质量 high。Image 2 自动高保真处理输入，省略 `input_fidelity`；不要添加不适用的 seed、SDXL 权重语法或 `xhigh`。实际返回尺寸仍要检查。

### 4. 恢复

每个 run 目录只对应一份任务指纹。`response.json` 将请求指纹、响应哈希和原始响应一起保存，恢复时核对归属；不能从其他任务复制响应来补空缺。更改提示词、图片或语言模型需使用新目录；已提交目录禁止再次 POST。

- `prepared`：尚未提交，可用原参数加 `--execute`。
- `submitting`／`unknown`：可能已生成；先查服务状态、宿主记录或已保存响应。脚本不会自动重试。
- `response_received`：响应已保存，修复本地处理问题后加 `--recover`，仅重新解析本地响应。
- `generated`：原图已保存，进入视觉检查；它不等于人工验收通过。
- `rejected`／`invalid_output`：保留记录，核对原因后再决定是否创建新任务。

401/403 检查认证和访问权限；400 检查字段；429 查看配额和限流。网络错误、5xx 或中断不证明服务端没生成；跨入口重试同样可能重复计费。安全拒绝按服务说明修正合规需求，不通过更换入口绕过。
