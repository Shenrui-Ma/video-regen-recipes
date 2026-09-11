# 生图：从角色到有序素材

此模板默认由 ComfyUI 生成图片，再交给后期；图片生成配置与剪辑参数独立。

## 取得与填写工作流

先读 [本地连接](../../../../skills/comfyui-reference-images/references/local.md)；服务器环境使用 [远程连接](../../../../skills/comfyui-reference-images/references/remote.md)。具体图按 [固定 Toolkit 关联](../../../../skills/comfyui-reference-images/references/toolkit.md) 获取：

```bash
python3 skills/comfyui-reference-images/scripts/resolve_workflow.py \
  sdxl-two-pass-cowboy-shot --output "$PROJECT/jobs/image.template.json"
python3 skills/comfyui-reference-images/scripts/prepare_graph.py \
  --template "$PROJECT/jobs/image.template.json" \
  --values "$PROJECT/jobs/image-01.values.json" \
  --output "$PROJECT/jobs/image-01.api.json" --output-node 12 \
  --manifest "$PROJECT/jobs/image-01.prepared.json"
```

命令从仓库根目录运行。第一条只取固定文件，第二条只填 JSON，都不会生成图片。可用 `--toolkit-dir` 指向已有配套库，离线时加 `--offline`。模型值必须来自实际节点枚举。

固定 SDXL 图的 values 键为 `seed`（整数）、`positive_prompt`、`negative_prompt`、`output_prefix`、`node_23_model_name`（放大模型）、`node_25_ckpt_name`（checkpoint）、`node_34_vae_name`、`node_27_lora_name`、`node_66_lora_name`、`node_68_lora_name`、`node_69_lora_name`。逐项填实值，不给未知模型编造名称。

这张图包含 1344×1344 首轮、模型放大、2352×2352 缩放和低降噪二次采样。它是可选的公开起点，不要求所有用户下载原有风格组合。若删 LoRA，要在本次图副本中正确重接 MODEL / CLIP 两路并登记修改；`strength_model=0, strength_clip=1` 仍有作用。现有 Anima / SDXL 工作流符合用途时也可直接使用，经 API 导出和依赖核验后保存本次图。

## 提示与批量生成

用 [提示骨架](../prompts/image.txt) 逐张替换。身份、服装、画风用相同描述，姿态与背景按镜头计划变化。没有参考条件时，相同 seed 或同一 LoRA 不能保证绝对一致。

每张 batch size 1；先用实际目标质量准备第一张，再批量。换 seed 时同时填写两个采样器，不保留旧值。模型文件缓存可以复用；角色、提示词或输入图哈希变化后，不可复用旧图片冒充新图。

提交、取图与异常恢复按 [批量调用路径](../../../../skills/comfyui-reference-images/references/batch-generation.md)。关键输出：`image id → graph SHA256 → prompt_id → SaveImage 节点 → 文件 SHA256`，重试只针对失败项。前景用完整原图；画幅不同由后期等比适配，不预先压成正方形。

若用户要求图像一致性，优先接兼容的参考分支或角色 LoRA；发现模型缺失时按 [模型发现](../../../../skills/comfyui-reference-images/references/model-discovery.md) 核查架构、基础模型、版本、下载文件和许可。无法获取的许可或模型是明确阻塞，不能静默换角色。
