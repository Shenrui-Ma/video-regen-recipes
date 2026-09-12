# 爻光原版复现对照

对应 [Issue #1](https://github.com/Shenrui-Ma/video-regen-recipes/issues/1)。本页补充原版运行证据，供已经用其他节点跑通生成的复现者对照。节点同名、参数接近、能够生成，都不证明上下文行为或输入相同。

## 先取这些材料

- [四段运行参数 JSON](yaoguang-run.json)：种子、Prompt ID、采样/发布区间、模型文件名及证据等级。
- [实际提示词原文](../prompts/yaoguang.historical.txt)：四段逐字相同，不是占位模板展开后的四套新词。
- [原生续接语义](native-continuation.md)：AV latent、音频换算、窗口、Trim及两种MotionContext的区别。
- [历史577帧驱动母片](https://github.com/Shenrui-Ma/video-regen-recipes/releases/download/heartache-reference-20260824/heartache-driver-577f.mp4)：160,208,343字节，作为Release附件提供，不放进Git历史。
- [参考画面校验记录](reference-check.json)：新脚本切出的四段，与找回的历史四段参考逐段比较解码后的YUV画面字节，全部一致。容器、音轨和文件SHA不同。

这些材料没有包含完整模型、原始latent或可独立安装的全部续接节点。新角色运行链仍需配置；不能把准备参考的脚本当成H3生成器。

## 1. 先固定驱动输入，避免577/578帧分歧

母片SHA256：

```text
e63386ab88bf4a11dc2fd859b0075099229cad44d77366a220c6e0bb0ba0ca0d
```

Python 3.9+、FFmpeg和ffprobe可用后，在仓库根运行。Windows把`python3`换成实际Python命令即可；文件名含空格时保留引号。

```bash
python3 templates/character-short/bit-by-bit-heartache/scripts/prepare_driver.py --input "heartache-driver-577f.mp4" --check-only
python3 templates/character-short/bit-by-bit-heartache/scripts/prepare_driver.py --input "heartache-driver-577f.mp4" --output-dir "../heartache-project/references"
```

输出目录必须不存在。脚本先校验母片SHA、577帧、1344×768和24fps，再切`[0,158)`、`[151,309)`、`[302,443)`、`[436,577)`；逐段检查帧数、尺寸、FPS和完整解码，写出`reference-manifest.json`。任何578/579帧输入都会报错，不悄悄删一帧凑数。

输出仅保留视频，使用libx264 CRF0。原版参考文件带AAC，但原版Ref2VA只连接了`GetVideoComponents.images`，没有连接其audio。移除参考文件音轨不改变这条图的实际音频输入；换成会读取该音轨的图则是新的行为。

复核解码画面哈希时要禁止FFmpeg补帧，例如：

```bash
ffmpeg -v error -threads 1 -i "../heartache-project/references/seg1_ref24_1344x768.mp4" -map 0:v:0 -an -pix_fmt yuv420p -vsync 0 -f hash -hash sha256 -
```

对照`reference-check.json`，不要对照包含旧AAC的文件SHA。FFmpeg默认同步策略可能为旧文件额外复制一帧，造成错误的不一致结论。

### 原始45fps视频当时怎样处理

原驱动为3840×2160，1105帧，约45fps。13.644438秒是历史场景变化检测`select='gt(scene,0.20)',showinfo`命中的第一个候选时间点，**不是已证明的节拍时间**。

历史先分别做24fps转换，再单独缩放；以下保留处理顺序，用新的输出文件名和防覆盖参数展示：

```bash
ffmpeg -n -ss 0 -i "driver.mp4" -t 13.644438 -vf "fps=24,setsar=1/1" -c:v libx264 -preset slow -crf 15 -pix_fmt yuv420p -c:a aac -b:a 320k -ar 44100 -ac 2 -movflags +faststart "part1_ref24.mp4"
ffmpeg -n -ss 13.644438 -i "driver.mp4" -t 10.911062 -vf "fps=24,setsar=1/1" -c:v libx264 -preset slow -crf 15 -pix_fmt yuv420p -c:a aac -b:a 320k -ar 44100 -ac 2 -movflags +faststart "part2_ref24.mp4"
ffmpeg -n -i "part1_ref24.mp4" -vf "scale=1344:768:flags=lanczos,setsar=1/1" -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -c:a copy "part1_ref24_1344x768.mp4"
ffmpeg -n -i "part2_ref24.mp4" -vf "scale=1344:768:flags=lanczos,setsar=1/1" -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -c:a copy "part2_ref24_1344x768.mp4"
```

两份**历史文件实际解码为327、262帧**，旧清单曾多记成328、263。之后命令请求part1的`[0,328)`和part2的`[12,263)`，超出尾部的上界并没有创造新帧，因此得到327 + 250 = 577帧。第二部分跳12帧是历史剪辑选择；目前没有充分证据将它归因为某个确定的节拍或通用去重算法。

现代FFmpeg、时间戳处理或再次封装后可能得到不同边界。以上用于解释历史处理顺序，**不承诺换版本重编码后与旧输入逐帧相同**。需要对齐原生成时，优先使用已找回的母片及画面哈希，不通过额外裁帧掩盖分歧。

## 2. 四段真正使用的提示词

[原文](../prompts/yaoguang.historical.txt)直接取自四份正式sidecar，逐字一致，SHA256为：

```text
3a3c183c678220df4506354e76fe11647c12d856fbb4a08843408b56cedf64f2
```

原运行没有逐段填写`CURRENT_SEGMENT_ACTION_AND_CAMERA`的四套文字，而是复用同一长提示词，换各段`<Video 1>`输入。人物外观/衣服在`subject_definitions`与`retention_analysis`，背景、动作与运镜在`<Video 1>`定义和`detailed_description`。不要把今天的通用模板反填结果当成当时原文。

原文也有局限，保留原样供对照：

- 四段summary都写6.583333秒，详细结束时间都写`00:6.7916`；第3/4段实际发布长度却为141帧。新创作可修正文案，但应另立版本。
- 虽有`<Audio 1>`和`fully_copy`，实际参考音轨未接入。CLI虽配置了`continue_audio=true`，原生节点本身没有这个开关，直接从前段AV latent续接原生音频；最终BGM是后期替换。
- “exact/frame by frame”等文字是目标，不是模型保证。

## 3. 参考图与模型参数

身份图为已有2352×2352 PNG，以ref_image输入，不是硬首帧。回收的CLI路径没有单独的上传前缩放/裁切步骤；运行节点仍按其自身实现处理参考图。`ref_image_size=match`来自回收CLI配置与重建API图，不能说该字段直接存在于最终sidecar。

仓库备用PNG移除了文本/EXIF元数据，压缩图像数据未改；公开文件SHA与原PNG不同，两个值均列在运行JSON中。

共同参数为1344×768、24fps、20步、res_multistep/simple、denoise=1.0、BasicGuider、无LoRA和clip projection。BasicGuider没有CFG字段，不补填CFG=1。

**音频VAE是FP32，不是双FP16 VAE。** 文件名见运行JSON。文件名相同仍不证明权重字节相同。

| 段 | Seed（十进制字符串保存） | 采样帧 | 发布区间，右端不含 |
|---|---|---:|---|
| 1 | `214235573447273430` | 158 | [0,158) |
| 2 | `1459903066845096071` | 192 | [22,180) |
| 3 | `7850450784904972903` | 175 | [22,163) |
| 4 | `8295737831123548902` | 175 | [22,163) |

大整数Seed不要经过JavaScript浮点数转换。每段Prompt ID与前驱关系另见JSON。

历史服务回读为ComfyUI 0.30.0、highvram，四段encoder route为local。**这四次运行的模型SHA、精确Torch/CUDA/Python、GPU型号和节点commit未完整固定，JSON用null表示未证实。** 注意力/缓存补丁也不根据启动参数中“没看到”就声明全部关闭。当前机器安装版本不能补写成历史版本；本次未在Windows/4060重新做GPU推理。

## 4. 续接与Trim

见[逐项语义](native-continuation.md)。原版将前段**完整canonical AV latent**交给原生`MiniMaxH3MotionContext`，后段头裁22帧再取指定发布长度，尾部还剩12帧未发布。`sample-visible=34`不是头裁34。

`audio_context_length=24`在该原生实现中对应1秒、40个音频latent步；源码固定按24fps换算，并不是读取任意视频FPS自动调整。不能据此推断其他节点也用相同单位。Save/Load是否带published-end字段，与MotionContext实际是否消费它，是两个问题。

本次提供参数语义、当前回收源码指纹与兼容检查清单。社区节点与原版是否等价仍须逐项验证，不把同名节点当同版本安装包。

## 5. 10/22样本与PR切点为何不同

历史接缝报告采用中央人物遮罩、背景MAE/Canny/dHash复制检测及母片映射：

- 第2段发布片的`[148..157]`与第3段canonical的`[0..9]`为10个匹配样本。
- 第3段canonical的`[153..174]`与第4段canonical的`[0..21]`为22个匹配样本。

这些是该报告的匹配结论，**不是整幅画面逐像素相同的哈希证明**。0-based闭区间覆盖量是10/22，不能将索引差9/21当样本数。

最终采用的是手工PR时间线，不是统一删10/22帧的检查分支：

| 段 | 60fps放置区间 | 被后段覆盖 | 最终可见前缀 |
|---|---|---:|---:|
| 1 | [0,395) | 0 | 395 |
| 2 | [395,790) | 22 | 373 |
| 3 canonical | [768,1205) | 55 | 382 |
| 4 canonical | [1150,1587) | 0 | 437 |

后段以InPoint=0放在更高轨道，覆盖前段尾部；不是将后段头部统一删除。第一个22帧覆盖是60fps时间基，换算为24fps是8.8帧，不能用整数删帧精确代替。395/373/382/437来自这个项目的放置与覆盖关系，不是自动接缝算法。

[现有剪辑脚本](../scripts/render_default.py)已按该可见时间线导出。这里`fps=60`仅重复/丢帧，不是RIFE；最终声音另接完整BGM。换角色重新生成后，需要重新确定切点。

## 6. 对照结果怎样贡献回来

请附上节点包URL/commit、环境版本、模型SHA、四段实际prompt与Seed、输入参考画面哈希、节点context/trim日志、canonical/published帧数及新的选片表。分开报告“节点能运行”“输入/语义相同”“新生成通过”“画面/声音审查”。原始latent依赖一段改变后，后续链也要重验。

本次已做离线单元测试、母片SHA/帧数检查、四段实际切片及完整解码、历史/新参考解码YUV流一致性校验。没有宣称新H3推理通过、Windows兼容或视觉/音频审查通过。
