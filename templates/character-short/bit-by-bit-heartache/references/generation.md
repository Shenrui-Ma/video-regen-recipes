# 换角色：按硬件分段的本地 H3 生成

默认素材的剪辑无需执行本页。对照爻光原版时，先读[复现材料](reproduction.md)：已补实际提示词、逐段参数、原生续接语义和可校验的577帧驱动附件。换角色时，采用[本地 ComfyUI](../../../../docs/comfyui-local.md)或[自托管远程实例](../../../../docs/comfyui-remote.md)，先确认实际安装的 H3 版本、模型和续接节点。

具体生图工作流优先使用 [ComfyUI Toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)的SDXL两次采样角色图，按[关联规则](../../../../skills/comfyui-reference-images/references/toolkit.md)取固定版本。当前Toolkit的H3对白图是独立分段，不能替代本页原生latent续接。

先读[部署与分段](deployment.md)。本页的四段表格全部属于历史对照；新任务由 Agent 根据设备和校准容量生成计划。历史 `prepare_driver.py` 仍只用于重切原版参考，不是新任务的通用分段器。

## 1. 准备参考

默认角色图可直接使用，也可换成新图。新图由[ComfyUI](../../../../skills/comfyui-reference-images/SKILL.md)、[GPT Image 2 high](../../../../skills/gpt-image2-reference-images/SKILL.md)或其他已配置入口准备；不要沿用默认角色的名字、服装描述或 LoRA。

驱动原片为3840×2160，1105帧，容器约24.5555秒，平均帧率约45fps。先读取实际元数据；它不是24fps或60fps源片。默认生成画布1344×768，和源片比例不同：历史使用直接缩放，新项目若改为等比补边或裁切，应明确记录并重新核对构图。

历史参考制作经过两次处理：

1. 在13.644438秒处分开原片，分别转24fps、1344×768。
2. 第一部分取 `[0,328)`，第二部分取 `[12,263)` 后拼回；实际解码为577帧，不能把计划上界579当实际帧数。

历史运行按下列区间拆分，不作为新任务默认。所有范围都是从0开始、右端不含：

| 段 | 577帧参考中的区间 | 帧数 |
| --- | --- | ---: |
| 1 | [0,158) | 158 |
| 2 | [151,309) | 158 |
| 3 | [302,443) | 141 |
| 4 | [436,577) | 141 |

这是历史参考准备方案，已改变源时间线。重新处理后必须核对真实帧数；未得到相同参考不能假称逐帧复刻。新角色／新视频可重新分段，7帧参考重叠不等于生成结果应该删7帧。

## 2. 固定基础采样

1344×768、24fps、20步，`res_multistep` / `simple`、denoise=1.0、BasicGuider。无 CFG 字段、negative conditioning、Turbo LoRA 或 clip projection，不凭经验补参数。

历史组合为 INT8 convrot Ref2VA 主模型、Qwen3VL 32B NVFP4 AWQ 编码器、视频 VAE FP16、音频 VAE FP32。查[H3 模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)及运行实例的模型枚举，记录实际文件哈希和节点版本，不根据名称认定权重内容相同。

使用[通用提示词](../prompts/ref2va.template.txt)，角色图作为身份参考，驱动帧作为动作和背景参考，均不属于硬首帧。参考视频经 `GetVideoComponents` 只连接 images；它的 audio 没有进入 Ref2VA，提示词不能声称真实音轨已经绑定。

## 3. 真实续接与裁切

```text
角色 LoadImage + 驱动 LoadVideo → GetVideoComponents.images
 → Ref2VA conditioning + joint latent
 → 首段直接采样；后段加入前段 canonical AV latent 的 Motion Context
 → 保存完整 canonical AV latent
 → 视频/音频分别解码 → 后段裁context并取发布长度 → 保存片段
```

所需能力为 `SaveMiniMaxH3AVLatent`、`LoadMiniMaxH3AVLatent`、`MiniMaxH3MotionContext`、`TrimMiniMaxH3MotionContext`。这些名称是原实现的节点合同，不代表任意 ComfyUI 安装都已具备。部署前核对 `/object_info`、代码和配套依赖；本包未提供这些适配节点的独立安装器。

| 段 | 发布帧 | 采样帧 | 视频context | 实际头部裁切 | canonical保留区间 |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 158 | 158 | 0 | 0 | [0,158) |
| 2 | 158 | 192 | 22 | 22 | [22,180) |
| 3 | 141 | 175 | 22 | 22 | [22,163) |
| 4 | 141 | 175 | 22 | 22 | [22,163) |

采样按 `17k+5` 对齐；后段裁22帧再取发布长度，仍有12帧canonical尾部未发布，**不能用采样减发布得到的34帧统一删头**。音频context参数24在本实现对应1秒、40个音频latent步，换实现须重新验证映射。

每个后段从前一段保存的完整 latent 取上下文，不从已发布 MP4 的尾部重编码。它可能引用未发布的尾部，所以同时保存 canonical 解码与发布片段，用于检查接缝。相同seed不证明两种续接路线相同。

## 4. 提交与返修

先完成首段的采样、两路解码和落盘，再继续后段。每段保存真实图、种子、Prompt ID、输入哈希、前驱latent哈希、canonical和发布产物。断线围绕原ID查队列/History；没有结果不代表没有执行。

逐段看人物、动作、背景与边界。前段重新采样会影响后续 latent 依赖；新建版本并重验依赖链。不得套用番剧独立分段的“只改一段就结束”规则。

生成完成后进入[后期](editing.md)。本包的爻光默认切点只适用于附带素材；换人物后必须重新确定接缝。
