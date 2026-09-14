# 新角色生成：当前可执行路径

从独立模板根目录按 [README](../README.md)执行。全部H3首段、续接、输入和后处理脚本都随包提供；无需其他个人Skill或私有Save/Load节点。

## 输入和条件

角色参考图→LoadImage→Ref2VA图像条件；577帧驱动→LoadVideo→GetVideoComponents.images→Ref2VA视频条件。驱动音轨不接入模型；正式配乐在发布画面拼接后重铺。参考条件提供身份和动作引导，不等于硬首帧或逐帧骨骼约束。

固定基础为1344×768、24fps、20步、res_multistep/simple、BasicGuider、denoise=1。固定模型与依赖见[环境说明](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/feee30d818aee9a6ee5f8ec098aea1f4d906c935/environments/h3/README.md)，角色文字使用[prompt模板](../prompts/ref2va.template.txt)。不得把历史爻光描述沿用于新角色。

## 采样与发布计划

`plan_segments.py`以实测容量求计划；采样帧按17k+5网格对齐。首段最多发布全部采样帧，后段保留22帧context成本，仅发布其后新画面；末段补齐网格的尾帧不进入发布结果。驱动切片与该段context+新增画面对齐，不能把历史四段的切点套到新计划。

例如实测最大107采样帧时，首段发布107，后续满段各发布85；总长由实际驱动577帧决定。这仅是容量示例。新机器先做完整首段和续接校准，记录模型常驻、RAM、显存与解码峰值。

## 真续接

1. Sampler产生完整联合AV latent。
2. Core `LTXVSeparateAVLatent`拆成video/audio，分别用Core `SaveLatent`保存，外部sidecar保存发布区间、前驱及SHA。
3. 下一段Core `LoadLatent`两路读取，`LTXVConcatAVLatent`合并，接到公开`MiniMaxH3MotionContext.context_latent`。
4. MotionContext的第二输出是INT裁切量，连`ImageFromBatch.batch_index`；length为计划发布帧数。
5. 保留完整latent与已经裁过context的发布画面，两者用途不同；后期只拼发布画面，不再次裁22帧。

Core LoadLatent会读成F32。这里只声明已核验F32往返，不泛化到其他dtype。私有canonical旧格式的字段及历史四段区别留在[历史续接记录](native-continuation.md)，不作为新安装的依赖。

## 运行和恢复

用`scripts/runtime/heartache.py`准备、检查、显式执行。每段runner先写提交意图，取得prompt_id后只围绕原ID查history；提交结果不明时禁止自动重投。用户取消后停止后续提交，完整保留已完成前驱。

采样成功但解码失败时，不应重新采样。已有两路latent可接无Sampler解码图恢复；确认header/shape、前驱、history和SHA后，完成原发布区间。修改前驱采样则必须新建版本并重验全部依赖下游。

## 参考背景与后处理预检

只借用人物身份而不保留参考图背景时，可先使用[去背景流程](background-removal.md)。保留alpha图，再明确合成纯色RGB送入H3，防止忽略alpha时读入隐藏背景颜色。该步骤不改变动作驱动、seed或采样规格。

按[媒体预检](media-preflight.md)在实际runner的PATH测试AAC和完整后处理。发布视频已成功而配乐失败时，仅恢复后处理，不重新采样。

## 后处理

拼接连续发布画面，原曲从时间线零点连续铺设、最后半秒淡出。每个阶段可生成第一至N段累计成片。技术校验包括区间连续、帧数、尺寸、24fps、视频画面未被换源、音轨覆盖时长、完整解码和SHA；身份、动作和接缝视觉效果由使用者确认。

[原版逐帧/逐字节对照材料](reproduction.md)与新角色再生成是两种验收目标：随机性、量化、硬件和不同分段都可能改变像素结果。
