# 逐段提交、断线恢复与验收

运行器使用同一套 ComfyUI API：默认连接本机 `http://127.0.0.1:8188`；远程使用者在当前终端设置 `COMFY_BASE_URL` 为自己的服务地址。服务、模型和输入素材都应已准备好，电脑上需有 Python 3、`ffprobe`、`ffmpeg`。支持 macOS、Linux、Windows。

## 1. 先只读检查

先把下面两个路径改成模板目录和自己的项目目录。API 文件来自 `build_episode.py --shot 01 --output "$PROJECT_DIR/build-01-v1"` 的首次构建，参数按该段计划填写。

```sh
TEMPLATE_DIR="/path/to/video-regen-recipes/templates/anime-dialogue-scene/mygo-ave-mujica"
PROJECT_DIR="/path/to/mygo-project"

python3 "$TEMPLATE_DIR/scripts/run_shot.py" --check \
  --workflow "$PROJECT_DIR/build-01-v1/api/01.json" \
  --run-dir "$PROJECT_DIR/runs/01-v1" \
  --frames 243 --fps 24 --width 768 --height 448
```

Windows PowerShell 把变量定义写成 `$TEMPLATE_DIR="实际模板目录"`、`$PROJECT_DIR="实际项目目录"`，用 `python` 替代 `python3`，并把每条多行命令合成一行、去掉行尾的 `\`。脚本使用 Windows 原生文件锁，不要求 WSL。

`--check` 只请求服务状态和节点信息，检查必需节点、输入接口、连线及服务端下拉框中的模型/素材名称。H3 的动态参考槽按服务声明的前缀、数量上限和类型检查，不允许拼错或越界的引用。它会在本机运行目录写检查记录，**不会提交任务、上传素材、下载模型或占用 GPU 推理**。检查通过不代表权重内容正确、显存足够或画质达标；这些要靠第一段试跑确认。

素材名不在列表：先在对应 ComfyUI 中上传/放好素材，确认加载节点能选中，再重跑检查。模型名不存在：按[模型查找说明](../../../../skills/comfyui-reference-images/references/model-discovery.md)确认架构、文件和存放类别，刷新服务后再检查，不用随便换一个相似名称。

## 2. 确认参数后只提交一次

把上面命令的 `--check` 改成 `--execute`，其余参数保持不变。每段独立一个运行目录；先完成一段试跑，再继续下一段。默认最终输出节点为 `92`，修改了图才用 `--output-node` 指定另一个 `SaveVideo` 节点。

脚本在提交前落盘 API 图、指纹、预期帧数/尺寸/FPS、唯一 client_id；收到 PromptID 后立即保存。已尝试提交的目录拒绝再次 `--execute`。

## 3. 看到 pending 或断线，只恢复原目录

```sh
python3 "$TEMPLATE_DIR/scripts/run_shot.py" --resume --run-dir "$PROJECT_DIR/runs/01-v1"
```

每次调用的工作时间预算默认 60 秒（可用 `--wait-seconds` 调小）；网络单次读取有超时。长任务返回 `PENDING` 是正常情况，稍后重复上面的恢复命令即可，服务端任务继续运行。退出码：`0` 为检查通过或媒体技术验收通过，`3` 为待恢复，`2` 为需处理的错误。

- 已有 PromptID：查原任务的 history/queue；不会重新提交。
- 提交响应丢失：按保存的 client_id 和图指纹，查 queue 与最近 1000 条 history。找到唯一原任务才接着跟踪。
- 两处都找不到：保持未知状态，检查原服务的历史/UI。不要以“没看到成片”为理由换目录重发；历史清理或服务重启会让客户端失去证据。
- 服务地址或稳定环境指纹变化：拒绝自动恢复，先回到原服务查任务。指纹是防连错环境的检查，不能证明同地址背后是同一台物理服务器。
- 明确失败后修图或改 seed：留好原记录，另建 `runs/01-retry-01` 再检查/执行。运行器从不清共享队列、杀进程或自动重投。

## 4. 成片必须经过两层验收

HTTP 成功、进度 100% 和存在输出文件都不等于交付成功。运行器只读取指定 `SaveVideo` 的唯一视频记录，通过 `/view` 下载成运行目录内固定的 `video.mp4`（或对应容器后缀），不把服务器文件名当成本地路径。

下载限额默认 2048 MiB，可用 `--max-download-mib` 调整；流式计算 SHA-256，下载不完整不发布文件。已下载的文件可在恢复时直接验收，不重新生成。验收包括完整解码帧数、尺寸、FPS、SAR 1:1，以及 FFmpeg 全段视听流解码。音频包的实际开始/结束时间需与画面时长匹配；24fps 时容许 0.1 秒编码延迟/填充，明显短音轨或迟入音轨会被拒绝。实际音频起止和时长写入 `verification.audio_timing`；不达标时停止，不自动丢音轨、截帧、拉伸或修复时间线。

`state.json` 的 `phase=media_verified` 只表示技术检查通过，音轨时长相符也不能证明台词完整或中间没有静音；`visual_review`、`audio_review` 仍为 `pending`。随后逐段看画面、听完整对白：身份/服装稳定、说话者正确、台词完整、语音自然、无明显声画错位，才进入[剪辑与交付](editing-and-delivery.md)。

## 认证与记录

需要 Bearer 认证时，仅从当前环境读取 `COMFY_AUTH_TOKEN`；不要把密钥写进 URL、API 图或仓库。远程认证要求 HTTPS，HTTP 重定向一律拒绝，以免凭据被带往别处。此可选方式不覆盖所有云平台登录协议；需要 Cookie/OAuth 的服务先配置其正式 API 接入方式。

运行目录是用户项目记录，应留在仓库外。脚本不持久化服务原始地址、认证值或服务器原始异常正文；API 图和媒体本身可能包含你填入的提示词和素材名，分享前仍需检查。

接口依据：[ComfyUI 服务路由](https://github.com/comfyanonymous/ComfyUI/blob/master/server.py)、[SaveVideo](https://github.com/comfyanonymous/ComfyUI/blob/master/comfy_extras/nodes_video.py)、[PreviewVideo 输出结构](https://github.com/comfyanonymous/ComfyUI/blob/master/comfy_api/latest/_ui.py)。当前官方 `SaveVideo` 的历史结果位于 `outputs[节点ID].images`；这是视频预览复用的键名，不是图片输出。版本不符时核对实际接口，不盲猜其他字段。
