# 生图后端怎么选（按用户的 Agent 与 provider 决定）

改参考图、换装、去背景、准备首帧这类任务，**先看用户在用哪个 Agent 产品、模型 provider 是什么**，再决定用哪种生图方式。总原则是「能走 CLI/API 就不走网页」，但前提是那条路对当前用户真的可用。

## 1. 决策顺序

1. **用户在用 Codex**，或用 Hermes / OpenClaw 这类开源 Agent 但**订阅走 Codex / GPT**
   → 优先 **GPT Image**：
   - 先用宿主内置的 `image_gen` 工具（无需 API key，生成物落在 `$CODEX_HOME/generated_images/`，再复制到项目目录）；
   - 该工具不可用时，用 Codex 的 `imagegen` 技能 CLI：`scripts/image_gen.py generate|edit --image … --out …`（需要 `OPENAI_API_KEY` + 网络）。
2. **用户用的是别的 provider** → 先查这个 provider 的 API 能力：
   - **有视觉 / 多模态能力**：它至少能承担“看结果、做画面验收”；如果它自身也提供出图或改图接口，就按它的接口做；否则往下走第 3、4 步找后端。
   - **没有视觉能力**：Agent 无法自己看图，只能做文件级技术检查；生图必须借外部后端，并把画面状态标为“待人工确认”（不要写成“已验证”）。
3. **provider 不能出图时，看用户已经登录的 chat**，优先级 **GPT → Gemini → 豆包**：
   - 先确认登录状态（页面右上角是否还有「登录」按钮，或跑对应 `status` 命令）；
   - 未登录时**把登录页打开给用户**，等他登录后再继续；不索取账号密码、不代登录、不碰 cookies；
   - 有适配器且支持“收图 + 落盘”的（例如 `chatgpt image --image <本地图> --op <目录>`），优先用它；没有就按对应站点的界面链路做（第 3 节给了豆包的实测链路）。
4. **都没有** → 本地 ComfyUI / SDXL（只需显卡，零账号，零边际成本）。
5. **还不行** → 请用户自备图片；不要用占位图或另一张素材顶替。

顺序不是“谁更高级”，而是“对当前用户门槛最低且能真正完成”。同一台机器上不同用户会落到不同分支。

## 2. 后端能力对照（2026-09 实测与核对）

| 后端 | 账号 / 订阅 | 能带输入图改图 | 能自动落盘 | 大陆网络 | 备注 |
| --- | --- | --- | --- | --- | --- |
| Codex 内置 `image_gen` | 无（随宿主） | ✅ | ✅ | 取决宿主 | 首选；部分会话未暴露该工具，需回落 CLI |
| `imagegen` CLI | `OPENAI_API_KEY` | ✅（`edit --image`） | ✅ | 需可达 OpenAI | 一条命令一张，最省事 |
| `chatgpt image --image --op` | ChatGPT 账号（多为付费档） | ✅ | ✅ | 视网络 | 适配器命令；本机实测被 opencli 1.7.22 的上传 bug 挡住 |
| Gemini / nano banana | Google 账号 | ✅ | 取决工具 | 不直接可用 | 版本名换代快，文档别写死具体版本 |
| **豆包** | 账号（扫码登录） | ✅ | ✅（第 3 节两种方式） | ✅ | 无 GPT 订阅时的主力 |
| 即梦 jimeng | 免登录可用文生图 | 仅界面 | ❌ | ✅ | 免登录只到文生图，改图要手动上传 |
| 通义 / 元宝 | 账号 | 视产品 | 视产品 | ✅ | 免登录状态不可假设可用 |
| 本地 ComfyUI / SDXL / Anima | 无 | ✅（需对应工作流） | ✅ | ✅ | 需显卡；换装/去背景靠 inpainting、RMBG 等工作流 |

## 3. 豆包完整链路（实测跑通，2026-09-16）

前置：用户在本机 Chrome 里登录豆包（扫码即可）；Agent 侧 `opencli doctor` 全绿。三次换装各用 50–75 秒，UI 显示「消耗 0」——但不要批量刷。

| 步骤 | 做法 | 关键点 |
| --- | --- | --- |
| 1. 打开会话 | `opencli browser <session> open "https://www.doubao.com/chat/?cxtarget=<唯一标记>"` | 唯一标记参数让 `osascript` 能精确定位到该标签，避免命中用户自己的其他豆包标签 |
| 2. 放图 | 图片进剪贴板（`osascript -e 'set the clipboard to (read (POSIX file "…") as «class PNGf»)'`）→ opencli 点输入框 → 激活该标签 → **真实 Cmd+V** | 不能用 `opencli keys "Meta+v"`（它不带 paste 语义）；先打一个字符确认光标在输入框 |
| 3. 确认 | 截图确认缩略图出现 | 没出现就重贴，不要盲发 |
| 4. 提示词 | 用下面的模板 | 关键是写清“哪些必须不变” |
| 5. 发送 | `click "#flow-end-msg-send"`，等 50–75 秒 | |
| 6. 取回 | 方式 A（推荐）：读 DOM 里的签名 URL → 本机带 `Referer` 下载；方式 B：页面内 `fetch` + `<a download>` | 方式 A 不受浏览器下载策略影响 |
| 7. 归档 | 改名存入项目目录，记录来源、原图、提示词、时间、结果哈希 | |

**取回结果的具体命令**（方式 A）：

```bash
# 从页面读取结果的签名 URL（过滤掉头像/图标，取大图）
opencli browser <session> eval "(()=>[...document.querySelectorAll('img')].filter(i=>i.src.includes('byteimg')&&i.naturalWidth>=1000).map(i=>i.src).join('\n'))()"

# 用 python/curl 带 Referer 取回（示例见仓库脚本习惯；不要把链接写进模板）
#   Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.doubao.com/'})
```

**改图提示词模板**（三次换装都用它，效果稳定）：

```text
只改<要变的部分>，其他都保持不变。把<对象>的服装换成：<具体服装描述>。
要求：脸型、五官、发型、发色、<其它身份特征>、姿势、手势、镜头角度和构图全部保持不变；
背景改成干净的纯白背景（用于视频参考图）；不要文字、水印或多余装饰；输出与输入同尺寸。
```

### 已知坑（豆包链路）

| 坑 | 现象 | 正确做法 |
| --- | --- | --- |
| `opencli keys "Meta+v"` | 只发按键、不带 paste 语义，图片不会进输入框 | 用系统级 Cmd+V（System Events），先确认光标 |
| `opencli browser upload <ref> <file>` | 等不到 `Page.fileChooserOpened` 而失败（1.7.22 实测） | 不要重试，改走剪贴板 |
| 多个豆包标签 | `osascript` 按 “doubao.com/chat” 匹配会命中别的标签，按键发错地方 | 给会话 URL 加唯一标记参数，只匹配它 |
| 输入框里的旧附件 | 合成注入的测试附件删不掉（点 × 会打开预览） | 别清残留，**直接新开一个对话** |
| 连续程序化下载 | 第二次 `<a download>` 被 Chrome 的“多文件下载”拦截 | 改用签名 URL + 本机 `Referer` 取回 |
| `opencli browser open` | 会新开标签，原会话可能停在 `about:blank` | 之后重新 `open` 目标 URL，或先 `state` 确认当前页 |
| 结果可能是 `blob:` | `curl`/`wget` 拿不到 | 在页面内 `fetch` 转换为可下载 URL，或读同元素的签名 URL |
| 推广弹窗遮挡 | Escape 关不掉，后续点击被吞 | `find --css "[aria-label*=关闭]"` 定位关闭按钮再点 |
| 点错页头按钮 | 把「下载电脑版」当图片下载，误下安装包 | 下载图片走签名 URL；误下的文件移入废纸篓而不是直接删 |

## 4. 记录与验收

- 项目记录里写清：Agent 产品与版本、模型 provider、本轮实际使用的生图后端、账号登录状态、时间、输入与输出哈希。
- provider 无视觉能力时：只做文件级技术检查，画面状态标“待人工确认”，不要把技术成功写成画面通过。
- 后端是网页链路时：注明“依赖登录态与页面结构，站点改版会失效”；长期稳定优先 CLI/API。

## 5. 边界

- 不伪造签名、不绕验证码、不代登录、不批量刷；网盘与登录墙资源按[图片与声音](assets-and-audio.md)交回用户手动下载。
- 第三方内容只在用户本机使用，不再分发；来源与许可按各模板的 `sources.md` / `LICENSES.md` 记录。
- 网页自动化只作为「没有 CLI/API 时」的降级路径；如果某个后端会被反复使用，优先把它做成适配器或改用有落盘能力的命令。
