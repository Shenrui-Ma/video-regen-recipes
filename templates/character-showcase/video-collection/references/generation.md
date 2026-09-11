# 从角色到动态立绘

## 一句话展开为项目

在用户自己的新项目目录保存 `plan.json`，至少包含：角色与服装约束、镜头编号、每镜头参考图/首帧图、动作、目标时长、实际模型与工作流版本、seed、任务状态、输出路径和后期模式。

默认三个镜头，每条目标约10秒：正面轻微呼吸与眨眼、身体小幅转向、轻微抬手或调整衣摆。服装、身份和总体画风保持一致，动作按原图姿态调整；不用一张不适配的图强做大幅转身。用户提供张数、动作或时长时优先采用。

这组镜头与动作默认值用于启动新项目。关联图的短片基线为864×1344、采样长度243、20steps、`res_multistep` / `simple`，并包含24→60fps的 RIFE 与原生音频。采样长度不等于发布帧数，不能直接以243/24填入源视频实际时长；经图中头尾处理和RIFE后，应记录实际输出再计算剪辑。

推荐工作目录：

```text
project/
  plan.json
  images/                   # 身份参考、各镜头首帧
  videos/                   # 各镜头原始 H3 输出
  audio/                    # 用户选择的配乐
  workflows/                # 本次实际使用的 API 图
  jobs/                     # 提交记录、状态、输出清单
  edit.json
  output/
```

## ComfyUI 参考图与首帧

调用 [ComfyUI 参考图 Skill](../../../../skills/comfyui-reference-images/SKILL.md)，让它负责工作流解析、模型选择、生成与失败恢复，不让用户手动准备完整素材包。

1. **连接分开。** 默认按[本地指南](../../../../skills/comfyui-reference-images/references/local.md)连接；指定服务器才按[远程指南](../../../../skills/comfyui-reference-images/references/remote.md)上传输入、下载输出。远程磁盘路径不是客户端可直接打开的路径。
2. **复用合适的图。** 通过 [Toolkit 关联规则](../../../../skills/comfyui-reference-images/references/toolkit.md)获取固定版本与校验哈希的工作流。若已安装合适 SDXL/Anima 图则优先使用；不存在才按模型发布方示例补齐。不要把仓库不存在的图当成已打包能力。
3. **匹配模型。** 按[模型发现说明](../../../../skills/comfyui-reference-images/references/model-discovery.md)查现有模型，再从 Civitai/Hugging Face 核实确切模型版本、家族、VAE/文本编码器/LoRA、许可与哈希。需要账号访问时使用用户已配置凭证；不将凭证写入模板。
4. **先锁身份，再做镜头。** 已有可用角色图优先作身份依据；纯文字先生成一致的身份参考，再确定各镜头首帧。角色名不等于图像条件，必须核对参考图片是否真的接入所选工作流。
5. **逐张登记。** 每张记录 `shot_id`、用途、来源、提示词、模型/LoRA、seed、`prompt_id`、输出路径与 SHA-256。同一服装的关键配饰和颜色写成共享约束。图片长宽比按 H3 图实际支持的尺寸准备，避免最后强行拉伸。

用户提供合适的首帧时，可跳过该镜头生图；仍检查文件和用途。不要以工作流存在或模型同名替代可运行检查。

## 本地 H3 独立 I2V

**本模板要求图像作为视频第一帧约束的 I2V。** 通用身份参考 Ref2VA 不等于严格首帧锁定；MyGO 对白模板的 Ref2VA 图不能直接充作这里的首帧 I2V。

通过固定版本解析器获取关联 Toolkit 的 `h3-i2v-live-portrait`：

```bash
python3 skills/comfyui-reference-images/scripts/resolve_workflow.py h3-i2v-live-portrait --output path/to/project/workflows/h3.api.template.json
```

命令从仓库根目录运行。复制 [H3 参数模板](../examples/h3-values.template.json)，按当前模型清单和已上传首帧填齐值；`null` 表示待填写，不能直接提交。共有12个绑定项：`diffusion_model`、`text_encoder`、`video_vae`、`audio_vae`、`first_frame`、`prompt`、`width`、`height`、`length`、`seed`、`output_prefix`、`rife_model`。`first_frame` 是 ComfyUI 可读取的输入文件名，不是任意客户端绝对路径。

使用 [批量生成与恢复说明](../../../../skills/comfyui-reference-images/references/batch-generation.md)离线绑定，再核对当前节点接口：

```bash
python3 skills/comfyui-reference-images/scripts/prepare_graph.py --template path/to/project/workflows/h3.api.template.json --values path/to/project/h3-values.json --output path/to/project/workflows/shot-01.api.json --output-node 145
```

完整占位符替换保留 JSON 的数字类型，不把 width/height/length/seed 写成字符串。视频输出节点为145，按实际历史返回中的输出列表取文件；不要用只识别其他视频保存节点的脚本强行执行。图仍依赖 `MiniMaxH3MemoryEfficientSageAttentionPatch`、RIFE 与视频输出相关节点；它不是无插件工作流。注意力补丁和 H3 runtime 的新环境兼容性需首次运行核对。

首次运行完成以下适配：

| 核对项 | 要记录的证据 |
| --- | --- |
| 工作流 | 固定 Toolkit 图与哈希匹配；本地保存本次实际 API JSON 及哈希 |
| 节点 | 从当前 ComfyUI `object_info` 核实类型、输入名和允许值，不猜 node ID |
| 图像条件 | 首帧文件实际连接到 I2V 条件分支；不能只有提示词或身份参考分支 |
| 模型 | 使用的 H3 权重、编码器、VAE、版本/量化与工作流兼容 |
| 参数 | 图实际支持的分辨率、时长/帧数、采样器、steps 和 seed |
| 输出 | 明确视频保存节点、输出定位方式及真实 FPS/帧数 |

尚未绑定的参数保留 `null` 并报告缺项，不复制其他题材的固定值。关联图来自具体独立 I2V 生成记录，仍需要在用户环境验证模型、插件与输入；获取成功不等于当前环境已能推理。首次适配结果留在用户项目中。

每条视频单独提交一张首帧和一个动作提示词。编号沿用 `shot-01` 等稳定标识，保存提交 JSON、返回 `prompt_id`、终态、实际输出文件和哈希。先生成第一条，确认输出文件完整并记录实际参数，再依次生成剩余片段；显存允许并不等于可以无约束批量并行。

断线后先查队列与历史：任务仍在运行就继续等待；已完成则取回已有文件；明确失败才对该镜头重试并保留旧任务记录。不要清空共享队列，也不要把旧作品按名字匹配后充当本次结果。

## 转给后期

原始 H3 视频保留原有 FPS 和分辨率，并记录关联图的 RIFE 处理。后期把实际时长填入 `edit.json`，统一输出为60fps；这一后期操作是常规重采样，不能声称又进行了运动插帧。

- D：每镜头一个 video clip。
- C：每镜头一个 image clip，紧跟相同 `pair_id` 的 video clip。保持该图确为对应视频的首帧来源。
- 选择音乐时写清路径、源起点、成片起点和是否循环；默认不生成 TTS，也不把视频模型的音轨冒充用户指定 BGM。

当用户只要求整理或检查模板时，以上均作为未来执行说明，不实际提交推理或生成媒体。
