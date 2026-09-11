# 角色视频合集

**一句话，把你喜欢的角色做成一组动态立绘，再剪成视频。**

> “用我喜欢的角色，做一支三个镜头的动态立绘合集。”
>
> “先展示每张原图，再接上它动起来的视频。”

Agent 会用 ComfyUI 准备参考图与首帧图，用本地 MiniMax H3 逐段生成，最后统一画布、转场和配乐。也可以直接提供已有视频，只做合集剪辑。

让 Agent 读取 [SKILL.md](SKILL.md) 即可开始。默认竖屏、三个独立镜头；角色、服装、动作、顺序和音乐都可以改。没有指定音乐时先输出无声版。

[生成链路](references/generation.md) · [剪辑规则](references/editing.md) · [视频合集示例](examples/video-collection.json) · [图→视频示例](examples/still-video.json)

原创配方：**Shenrui Ma（四倍体果蝇）**。工作流从关联 Toolkit 获取，首次运行由 Agent 核对本地模型与节点。参见[来源与验证范围](sources.md)。
