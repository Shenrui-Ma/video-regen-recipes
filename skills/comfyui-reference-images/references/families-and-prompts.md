# 模型家族、工作流和提示词

## 先选家族，再组合节点

| 家族 | 最小结构 | 不要默认继承 |
|---|---|---|
| SDXL | `CheckpointLoaderSimple` 提供 MODEL/CLIP/VAE → 文本编码 → 该版本的 latent/采样器 → `VAEDecode` → `SaveImage` | Refiner、独立 VAE、clip skip、多重 LoRA、修脸和高分辨率二次采样 |
| Anima | `UNETLoader` + `CLIPLoader` + `VAELoader` → 对应版本的文本编码、latent、采样 → 解码保存 | SDXL 编码器/VAE、SDXL 的空 latent 或 loader 参数、旧 Preview 图的默认设置 |

SDXL Base 可单独生成，Refiner 是另一个可选阶段。微调模型是否内含兼容 VAE、是否需要特定编码方式，应看该发布版说明。[SDXL 官方模型卡](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)

Anima 官方示例分别加载扩散模型、Qwen-3 0.6B 文本编码器、Qwen-Image VAE。它们的 loader 参数和 latent 类型以对应版本的官方图与实时 `/object_info` 为准；不要凭节点名自行填 `type`。模板可能使用子图，需展开检查。[ComfyUI Anima 示例](https://docs.comfy.org/tutorials/image/anima/anima)

Anima Base、Aesthetic、Turbo 是不同配置：Base/Aesthetic 的常规采样设置不能移植给蒸馏 Turbo；Aesthetic 的提示词也不应照搬 Base 的整组质量标签。选择精确版本后读取采样与提示词说明，记录实际值，不自动追新。[发布方模型卡](https://huggingface.co/circlestone-labs/Anima)

## 提示词写法

先把用户要求拆成六项，再按底模习惯组织：人物可见特征、服装、姿态表情、景别机位、场景光线、画风。保留用户的固定要求，不附加私人角色、艺术家标签组合或未要求的装饰。

通用内容示例（需要按选中模型转换，不是万能质量咒语）：

> 一位短棕发、绿眼睛的成年角色，穿深蓝夹克和白色长裤。全身站在浅色背景前，双手自然垂下，面向镜头，柔和均匀光照，清晰的动画线稿。

- **SDXL：**先读具体 checkpoint 的示例和标签习惯。用少量准确标签或短句；仅保留该模型需要的质量标签与 LoRA 触发词。不把某个微调分支的评分标签推广到全部 SDXL。
- **Anima：**可使用标签、完整自然语言或混合提示。使用自然语言时把外观与动作关系写清楚；按所选版本决定质量标签。不要照搬 SDXL 权重强度或某个版本的整段负面词。[Anima 提示说明](https://huggingface.co/circlestone-labs/Anima#prompting)
- **负面提示：**只写与本图有关的缺陷或排除项；正负描述不能互相矛盾。不添加会改变用户意图的题材或画风约束。
- **LoRA：**先确认兼容底模，再采用作者建议的触发词和强度范围；从少量必要 LoRA 开始。逐一检查 MODEL 与 CLIP 链路，不认为每种 LoRA 都有 CLIP 权重。

## 图像用途决定约束

| 用途 | 画面重点 | 验收 |
|---|---|---|
| 身份参考 | 头发、脸型、眼睛、标志配饰与固定服装清晰可见 | 不遮脸；无多余人物；不靠角色名字代替外观 |
| 首帧/尾帧/中间帧 | 明确景别、姿势、左右关系、背景锚点和留白 | 镜头之间身份和空间连续；禁止未要求的拼图 |
| 场景参考 | 地标位置、光源方向、时间、色调 | 与角色帧可组合，不自带无关人物 |

已有参考图时选择该家族支持的图生图、局部重绘或参考条件节点，并核验实际连线。文字描述不能替代视觉条件。固定 seed 有助比较，不能保证跨版本像素一致。

二次采样和修脸是独立阶段：从目标 `SaveImage` 反向追踪；区分像素放大、图生图再采样和局部修复。比较方案时使用同一张输入及哈希，每次只改变一个机制。生成式修复可能改变身份，必须再次验收。
