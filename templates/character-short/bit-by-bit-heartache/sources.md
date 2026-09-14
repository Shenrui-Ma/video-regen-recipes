# 来源与验证

原创配方与制作整理：**Shenrui Ma（四倍体果蝇）**。

依据贡献者提供的2026-08-24至25日生成记录整理。历史示例使用其爻光档案中的角色图、动作参考、替换音乐与最终剪辑选源；没有收录私人脚本配置、服务器信息、历史任务ID、工程文件或角色图内嵌工作流。

## 默认素材

- 角色图为已有爻光参考图；内嵌数据表明保存过SDXL生图配置，但缺少原始生图任务与权重哈希，不能声明由GPT Image生成或可逐像素重做。
- 动作参考由贡献者本地提供，未核实到可靠原发布网址，不猜作者或来源链接。
- 默认音乐为贡献者指定的替换音轨，未进行声线转换；图片、视频和歌曲的权利分别归其权利人，仓库不将它们重新许可为MIT素材。
- 四个H3剪辑源为已有生成产物。公开副本流拷贝保留视频数据、去掉音轨和容器元数据；角色PNG去掉文字/EXIF，图像压缩数据不变。实际副本哈希见[素材清单](assets/default/manifest.json)。

## 本次与历史的区别

最早版本以历史素材和PR时间线整理为主。0.2.0模板随后在既有Linux/A100环境完成两次真实首段试跑：原人物参考图，以及RMBG去背景后合成白底的参考图，均为107帧、24fps。视频技术验收和下载读回SHA见[首段实跑记录](references/first-segment-validation.json)。0.3.0吸收这些运行修正；它的代码测试不等于又完成了一次GPU推理。

原生latent续接、22帧头部裁切、后两段canonical选源和1587帧时间线来自历史记录。没有把已发布视频重编码续接、早期独立四段或旧RIFE母版混入当前方法。

当前[环境依赖锁](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/dependencies.lock.json)提供H3模型权重的固定来源、大小和SHA，安装脚本按固定版本获取公开节点。权重、私人latent和成片不内嵌轻量包。历史剪辑素材仅用于用户明确授权的重剪；新角色仍需实际生成，不能仅凭相同seed宣称逐像素复现。

技术依赖：[MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3)、[模型卡](https://huggingface.co/MiniMaxAI/MiniMax-H3)、[ComfyUI](https://github.com/Comfy-Org/ComfyUI)、[FFmpeg](https://ffmpeg.org/)。可选RTX VSR和RIFE依其实际实现与许可使用。
