# 自动关联 ComfyUI Toolkit

涉及 ComfyUI 时，先检查 [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit) 的[工作流目录](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/blob/main/workflows/index.json)及对应说明。该仓库维护具体节点图和执行工具；Recipes 负责题材、提示词、输入资产、时间线和验收要求。

当前可复用图由 [toolkit.lock.json](toolkit.lock.json) 固定 commit、路径和SHA-256。已验证配方使用锁定版本；浏览最新目录只用于发现新候选，不能静默替换旧图。

## 获取工作流

设置 `SKILL_DIR` 为本 Skill 目录、`PROJECT_DIR` 为自己的项目。需要角色图时选择 `sdxl-two-pass-cowboy-shot`；需要独立H3对白时选择 `h3-ref2va-dialogue`。

```bash
python3 "$SKILL_DIR/scripts/resolve_workflow.py" sdxl-two-pass-cowboy-shot --output "$PROJECT_DIR/workflows/character.api.template.json"
```

有本机 toolkit checkout 时设置 `COMFYUI_TOOLKIT_DIR` 或加 `--toolkit-dir`；离线可加 `--offline`。解析器优先复用已校验的输出文件，然后使用指定本机仓库，否则读取锁定的GitHub文件。哈希不符就停止，不覆盖或改用最新文件。

下载文件仍是带占位符的模板。按工作流自己的参数说明填写模型、素材、提示词和种子，再检查 `/object_info` 后执行；获取工作流不代表下载模型、安装节点或开始推理。

Toolkit 目前没有收录所有H3续接模式。需要原生AV latent/Motion Context时，不能用独立对白图顶替；继续按对应配方检查实际实现，缺少时报告缺项。

当前用户要求与配方的固定参数优先。Toolkit 的通用默认值不能覆盖配方中的seed、采样、音频或验收规则。Recipes 使用 `COMFY_BASE_URL` 时，可将该运行时值传给 Toolkit runner 的 `--host`，不另写机器地址。
