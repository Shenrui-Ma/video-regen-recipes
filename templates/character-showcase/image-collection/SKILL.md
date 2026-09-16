---
name: character-image-collection
description: 一句话指定角色与主题，调用本地 ComfyUI 生成成组角色图，再制作缩放模糊展示或纯交叉溶解的竖屏图像合集视频；支持已有图片与局部重做。
version: 0.1.0
author: Shenrui Ma（四倍体果蝇）
license: "See LICENSES.md for component terms"
platforms: [linux, macos]
---

# 角色图像合集

目标是交付视频、实际使用的图片和执行台账。按以下顺序推进；本模板的动态效果来自剪辑，不需要运行视频模型。保留完整仓库或同时安装引用的共用目录。

## 1. 将一句话变成计划

用户指定值优先，其次是当前项目设置，再用下列默认值。普通参数可直接写进计划，不逐项询问。

| 项目 | 未指定时 |
| --- | --- |
| 角色 | 当前请求或项目已选角色；都没有时只补问角色，不偷换成示例人物 |
| 主题 | 同角色、同服装的日常场景，改变姿态和背景 |
| 张数 / 总长 | 6 张 / 36 秒 |
| 模式 | A：原始缩放与模糊；“纯溶解 / 不要缩放”选 B |
| 成片 | 1080×1920，60fps，同源模糊背景，保比例居中前景 |
| 配乐 | 使用用户指定或项目已授权配乐；没有则无声，不自动抓热门歌 |
| 结尾 | A 最后 1 秒音画淡出；B 默认不淡出 |

新建独立项目，存 `request.json`、`shots.json`、`models.json`、`jobs/`、`images/`、`edit.json`、`output/`。已存在的图片和成片只读；输出用新文件名。

从 [镜头计划](examples/shots.json) 建立明确顺序。每项固定 `id`，包含角色身份、服装、景别、动作、背景、提示词、seed、目标文件和生成状态。需要换顺序时移动整项，不能只改编号。需要补图时只生成缺少的项；不要按目录“最新文件”猜结果。

## 2. 调用 ComfyUI 生成图片

执行 [ComfyUI 参考图 Skill](../../../skills/comfyui-reference-images/SKILL.md)，细化步骤见 [生图与恢复](references/images.md)。

1. 默认检查本地实例；只有用户配置服务器时进入远程分支。盘点实际模型和节点。
2. 优先选用户已有兼容图；否则按 Toolkit 固定索引取得 `sdxl-two-pass-cowboy-shot`。其景别可改，不能把名称当成固定人物。Anima 需求则查相应已验证图，不把 SDXL 权重或 LoRA 塞进 Anima 图。
3. 为第一张绑定 checkpoint、VAE、兼容 LoRA、正负提示、seed 和唯一前缀；完整渲染 API JSON 后检查 `/object_info`。缺少模型按参考图 Skill 主动在 Civitai / Hugging Face 查找兼容文件及许可、哈希。
4. 单次提交，立即保存 `prompt_id`；等目标 SaveImage 成功，下载最终原图。保留二次采样输出，不误用中间预览。
5. 文件与内容可接受后再顺序生成剩余项，复用模型组合，逐张独立 seed。用户禁止视觉检查或 Agent 无看图能力时，视觉状态记 `pending`，按该限制继续，不能写成已验收。
6. 角色或姿态不合要求时只修该项；网络断开先查旧任务，禁止整批重发。

已有图片可跳过对应生图项。用户提供图作为身份依据时要连接兼容参考分支；纯文生图没有参考输入，不能声称已锁定上传图身份。

## 3. 剪辑成视频

完整算法由 [合集剪辑 Skill](../../../skills/character-showcase-editing/SKILL.md) 执行。读取 [参数说明](references/editing.md)，从 [A 配置](examples/edit.dynamic.json) 或 [B 配置](examples/edit.static.json) 复制 `edit.json`，将实际图片路径按顺序填入。所有路径相对该 JSON 所在目录。

从仓库根目录执行，`PROJECT` 指向本次项目：

```bash
python3 skills/character-showcase-editing/scripts/showcase.py "$PROJECT/edit.json" --plan
python3 skills/character-showcase-editing/scripts/showcase.py "$PROJECT/edit.json" --check
python3 skills/character-showcase-editing/scripts/showcase.py "$PROJECT/edit.json" --render
```

只有用户要求制作成片且上游输入齐全时才运行 `--render`。整理模板或只检查文件时止于 `--plan` / `--check`。示例图片未附带，因此原样 `--check` 报缺图是正常行为，不应伪造图片绕过。

## 4. 恢复与交付

- 生图成功、剪辑失败：修编辑配置后重剪，不重新生图。
- 已有 `prompt_id`：恢复查询同一任务。提交结果未知：标 `unknown`，核对队列与 history，不能当失败自动重试。
- 图片数量变化：同步有序列表并重算时间线；A 固定总帧数，B 补足重叠时长。不要把两者算法混用。
- 只换配乐：复用已确认的画面流，更新音轨与记录。
- 完成条件：本次新输出编码成功；交付 MP4、实际图片、`edit.json` 和生成/剪辑台账。技术检查、内容检查、历史证据分别记录，不能继承旧 manifest 的成功状态。

配方：**Shenrui Ma（四倍体果蝇）**。
