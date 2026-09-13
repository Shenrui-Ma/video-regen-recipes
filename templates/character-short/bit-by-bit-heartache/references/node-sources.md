# 工作流节点来源

对四份恢复图的 `class_type` 去重，共20类：16类属于 ComfyUI Core，4类非 Core，分属两个包。完整逐类映射在 [node-sources.json](node-sources.json)。此清单范围是 H3 原生生成链；可选生图、RIFE、超分须另按选用图列依赖，不混进必需安装列表。

## 非 Core：逐项来源

- `MiniMaxH3MotionContext`：上游 [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)。已从现存安装目录核对远端 URL、commit `f80e36bc1d7887a143b12e6645313fd6b9cd2aee`、顶层 `__init__.py` 及 GPL-3.0 许可。包目录名 `H3MotionContextOfficial` 是本地命名，不表示 ComfyUI 官方 Core。
- `SaveMiniMaxH3AVLatent`：作者本地 `HermesH3Continuation/__init__.py`，保存 canonical 联合 AV latent 与元数据。
- `LoadMiniMaxH3AVLatent`：同一作者本地包，读回上述格式。
- `TrimMiniMaxH3MotionContext`：同一作者本地包，按实际头裁与发布长度同步裁画面、音频。

后三项源码已定位并核对 SHA-256 `edf270a641808282f5d3ff51a260518821a59ad1dffcd27e23e6f6794787c573`。但没有独立公开仓库、发行包或已确认的软件许可；下载 URL 和许可在 JSON 中保留 null。源码就在作者环境中，不应让复现者自己按名称搜索，也不能声称已经可公开安装。它们与上游另一套 Save／Load／Trim 类名和行为不同，不能无验证替换。

## 上游包的安装与补丁边界

在使用者已批准的 ComfyUI 安装目录执行：

```bash
git clone https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context.git "$COMFY_DIR/custom_nodes/H3MotionContextOfficial"
git -C "$COMFY_DIR/custom_nodes/H3MotionContextOfficial" checkout --detach f80e36bc1d7887a143b12e6645313fd6b9cd2aee
```

这两条只取得上游固定源码，不完成整个配方。保留上游 LICENSE；读其 README 和依赖声明，重启自己的实例后核对 `/object_info`。包需要 `nodes.py`、`patch_layout.py`、`patch_payload.py` 与注册入口，不能只复制一个文件。

现存远端安装的 `nodes.py` 有本地修改。上述 commit 只固定当前安装目录的基底，不是当年运行锁；上游 checkout 不包含这份修改。旧缓存源码、当前修改源码和历史真实版本三者分开记录。完整补丁发布与兼容测试尚未完成，不把安装上游说成复现当年环境。

## Core 归属

`UNETLoader`、`CLIPLoader`、`VAELoader`、`VAEDecode`、`LoadImage` 在 `nodes`；采样相关节点在 `comfy_extras.nodes_custom_sampler`；`VAEDecodeAudio` 在 `comfy_extras.nodes_audio`；视频读写在 `comfy_extras.nodes_video`；`MiniMaxH3ReferenceToVideo` 在 `comfy_extras.nodes_minimax_h3`。

这些归属由实际源码和已存 `/object_info` 对照，不靠节点名称推测。当前核查 Core commit 为 `6f7cd7fceaaf60d2669b554936394a7412c6fde5`（[源码](https://github.com/Comfy-Org/ComfyUI/tree/6f7cd7fceaaf60d2669b554936394a7412c6fde5)）；不是历史环境锁，也不是与所有自定义补丁完成兼容验证的保证。普通旧版 Core 不一定具备 H3 能力。
