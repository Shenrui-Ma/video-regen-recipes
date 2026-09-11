# NovelAI 官方 API 接入

核对日期：2026-09-11。官方资料已核对，生成未实跑；下面将接口事实与本客户端约束分开。

## 认证与模型

在官方账户设置获取 Persistent API Token，由宿主安全注入 `NOVELAI_API_KEY`。客户端发送 `Authorization: Bearer <token>`，不保存令牌、不读取密码。创建新令牌会使旧令牌失效，不要为检查连通性擅自重置。[账户设置](https://docs.novelai.net/en/text/usersettings/account/)

**模型展示名不等于 API ID。** 当前官方模型页面列出 V5、V4.5、V4 等系列；Image OpenAPI 的 `model` 是普通字符串，没有完整模型枚举，仅在标签接口示例出现 `nai-diffusion-3`。不能据此推导 V5/V4.5 的 ID 或默认退回 V3。[官方模型页面](https://docs.novelai.net/en/image/models/) · [官方 schema](https://image.novelai.net/docs/doc.json)

获取缺失配置的顺序：查当前官方 API 说明 → 使用用户已授权的官方网页成功请求中脱敏后的生成 body → 仍没有则报告缺项。只保留生成字段；不要导出整份 HAR、Cookie、Authorization 或账户请求。不要为了捕获请求额外触发计费。sampler/action 的模型兼容性同样需核对；本地校验通过不能证明服务端支持。

## 基础调用

```text
POST https://image.novelai.net/ai/generate-image
Authorization: Bearer <由环境注入>
Content-Type: application/json
Accept: application/zip

{"input": "...", "model": "<verified API ID>",
 "action": "<verified action>", "parameters": {...}}
```

核心参数是宽高、张数、steps、scale、sampler、seed、negative_prompt。结构化提示可使用 `v4_prompt` / `v4_negative_prompt`，包含 `caption.base_caption` 与 `caption.char_captions`；名字中有 v4 不代表可随意套用所有代际。图生图需要 `image` 的图片 base64 和 `strength`、`noise` 等适配参数，不能把本地路径或 data URL 当图片数据。普通图生图与 inpaint 的嵌套 `img2img` 结构不同。[官方接口定义](https://image.novelai.net/docs/doc.json)

客户端采用非流式 ZIP 输出。当前 schema 也提供 JSON 图片响应和 SSE 接口，本客户端不使用它们。`x-correlation-id` 是排查请求用的六位字母数字标识，**不是防重复计费的幂等键**。[官方 API](https://image.novelai.net/docs/index.html)

### 可运行客户端的范围

- 只发一张 PNG；`action=generate` 或 `img2img`。不增大尺寸、降级模型或改质量参数。
- 宽高是 64 的倍数且各不超过 2048，steps 1–50，scale 0–20；这些是客户端保守边界，不是服务套餐上限，也不保证免费。
- 输入 PNG 必须预先按目标尺寸准备好，保持比例、明确裁切/补边；脚本不会悄悄拉伸。
- `request.json` 必须来自已核对的配置。骨架中的模型与采样器占位符故意不能提交。
- 请求、ZIP、图片和 `state.json` 留在用户项目。目录不允许复用提交；网络请求无自动重试，重定向被拒绝。

图生图在已验证请求上设置 `action=img2img`，并用标准库把底图编码到 `parameters.image`：

```python
import base64
from pathlib import Path
request["parameters"]["image"] = base64.b64encode(Path(input_png).read_bytes()).decode("ascii")
```

显式设置 `strength`、`noise`，并根据该模型成功配置保留其他必需字段；不要只写一条 base64 就认为链路已完备。

## 参考能力怎么选

| 需求 | 官方功能 | 边界 |
|---|---|---|
| 改底图、尽量保留构图 | Image2Image | 会重绘；不是独立身份约束 |
| 参考色彩、视觉风格、部分构图 | Vibe Transfer | 不能当作精确角色锁定 |
| 更明确地沿用角色或风格 | Precise Reference | 有额外费用，仍需验收；多角色参考可能混合 |

**Vibe Transfer：** 官方提供 `POST /ai/encode-vibe`，输出二进制编码；生成参数有 `reference_image_multiple`、`reference_information_extracted_multiple`、`reference_strength_multiple`。V4 及以上有编码缓存，改变提取量可能再次计费。不要将整份 `.naiv4vibe` 文件或其 JSON 当作纯编码塞入数组。要核实该模型需要原图还是编码，以及缓存格式，才可提交；缓存键至少含模型、输入图 SHA-256、提取量和编码配置。[Vibe Transfer](https://docs.novelai.net/en/image/vibetransfer/) · [API schema](https://image.novelai.net/docs/doc.json)

**Precise Reference：** schema 提供 `director_reference_images`、`director_reference_descriptions`、`director_reference_information_extracted`、`director_reference_strength_values` 与 `director_reference_secondary_strength_values`；数组必须逐项对应。API 的 CR 描述注明 `character` 或 `character&style`，图片适配 1024×1536、1536×1024 或 1472×1472 并补黑边。官方产品页面还有 Style Reference，不能凭 UI 名字猜其 API 枚举。选用哪代模型、参考组合是否可与图生图/Vibe 同用，要以当前官方支持或成功配置为准；schema 包含字段不等于所有模型都支持。[Precise Reference](https://docs.novelai.net/en/image/precisereference/) · [API schema](https://image.novelai.net/docs/doc.json)

高级参考功能目前提供接入说明，**未纳入附带客户端**。需要时先拿到该功能的完整已验证请求和费用范围，再扩展适配器与测试；不能删除参考字段伪装成已经完成。缺少配套信息时可交付提示词和底图准备结果，并明确尚未生成。

## 失败与恢复

| 状态/现象 | 下一步 |
|---|---|
| 本地校验失败 / 无凭据 | 未提交；补足输入，不改成其他模型 |
| 401/403 | 检查令牌与账户权限，禁止打印令牌或自动重新登录 |
| 余额不足 / 费用超范围 | 停止付费步骤，报告需要的账户或预算处理 |
| 400/422 | 对照当前 schema 和配置修正字段，不用循环请求猜参数 |
| 429 | 停止本轮提交，不自动重试或开启并发 |
| 超时 / 断线 / 5xx / `submission_unknown` | 可能已生成或计费；保留状态与 correlation ID，核查账户/服务信息。无确证时不重发 |
| `response_saved` / 本地解包失败 | 保留 ZIP，本地修复后恢复，不重新生成 |
| `downloaded_needs_visual_review` | 网络与文件检查完成；打开图片做视觉验收 |

只重新解包已保存响应：

```sh
python3 "$SKILL_DIR/scripts/novelai_image.py" --run-dir "$PROJECT_DIR/runs/frame-001" --recover
```

恢复要求 `response/` 中同时存在 ZIP 与 `receipt.json`。客户端原子保存这组文件，收据绑定请求指纹、提交标识和 ZIP 指纹；即使保存成功后状态更新中断，也能核对归属后恢复。散落的 ZIP、其他任务的响应、`prepared` 或 HTTP 失败状态都不能直接认作已生成结果。没有有效响应时该命令不会生成图片。

重新提交必须先处理上一笔的未知状态，并确认再次计费在授权范围；用新目录记录关联，不删除旧状态来绕过保护。本工具的防重复范围是同一 run 目录，不是跨目录/跨机器的服务端幂等机制。

文件检查覆盖 ZIP 路径、链接、数量、压缩膨胀限制，PNG 签名、块 CRC 和尺寸；完整像素解码与内容合格仍依赖图片查看工具。服务返回异常时不输出原始错误 body，以免泄漏提示词或账户内容。

## 验证记录

```sh
python3 -m unittest discover -s "$SKILL_DIR/tests" -v
```

离线测试使用内存响应与临时目录，不读取真实令牌，不发出付费请求。覆盖一次提交、未知状态防重发、ZIP 恢复、响应类型、路径攻击及输出检查。真实账户认证、当前模型 ID、计费、高级参考配置和生成质量均需实际任务分别核实。
