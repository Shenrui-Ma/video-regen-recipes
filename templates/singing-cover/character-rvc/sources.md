# 来源、致谢与公开范围

本模板根据《莫斯提马中文 RVC 训练与翻唱 保姆级溯源资料包 v1.0》重新提炼为**指定角色通用模板**。配方与历史工程整理：**Shenrui Ma（四倍体果蝇）**。本次只读取源包文档、官方代码快照与旧脚本，不运行旧总控，不复制其破坏性恢复或清理行为。

本次源包核验：**298 项 payload 校验通过**；ZIP SHA-256：`46ebbea7bb7f5fb811a3e2a1e8758a62b7d23843e178b2d004044f0af36d7d57`。这是来源归档校验，不是重新训练、模型加载或音频听审的证据，也不是展开文件或重新打包 ZIP 的预期哈希。

## 致谢与来源

| 来源 | 用途与边界 |
| --- | --- |
| [RVCProject / RVC-Project](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/tree/4338f12c3c28c80b3ac015e2d0df66c41592746d) | 感谢官方 RVC 实现；本模板固定此 commit，代码许可 MIT 不覆盖全部权重与录音 |
| [VoiceConversionWebUI 资产入口](https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main) | HF HuBERT、RMVPE、v2 预训练与 mute 来源索引；main 可变，原下载 revision 未恢复，需独立查许可和固定 revision |
| [BV17a411d7ex](https://www.bilibili.com/video/BV17a411d7ex/) | 历史中文源：【明日方舟中文语音】莫斯提马【CV. 若舞】；转载/整理合集，不是官方账号，不是 RVC 成品 |
| [PRTS 莫斯提马](https://prts.wiki/w/莫斯提马)、[语音记录](https://prts.wiki/w/莫斯提马/语音记录) | 可信度需按具体页面核对的资料站；转载页简介所指来源，不是训练许可。历史直取曾遭 403 |
| [明日方舟](https://ak.hypergryph.com/) | 角色与游戏权利主体的官方入口；感谢原角色中文配音若舞及游戏权利主体（鹰角网络等，具体权利以各项声明为准） |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp)、[FFmpeg](https://ffmpeg.org/)、[ffprobe](https://ffmpeg.org/ffprobe.html) | 来源元数据、合法取得材料后的解码和技术检查工具，工具可用不代表获得素材使用权 |
| [共享分离方法](../girls-band-ddsp/references/processing.md) | 仅复用 pymss 分离/声部听审方法；模型及配置来源、许可见其 [dependencies](../girls-band-ddsp/model-catalog/dependencies.json)，不需要 DDSP 权重 |

以上是可追溯链接，不声称本次逐页联网核验成功。感谢若舞的原始角色表演，不将其列为此合成演唱的参与者或背书人；合成歌曲应披露 AI 音色转换，原歌手、歌曲、录音、角色和声音权益分别处理。

## 证据分层

- 官方接口依据：源包 `evidence/remote/app/rvc/` 中 `train/preprocess.py`、`train/dataset/extract_f0.py`、`extract_hubert_feature.py`、`train/train.py`、`train/utils.py`、`train/train_index.py`、`infer/hubert.py`、`infer/vc/modules.py`、`infer/vc/pipeline.py` 与配置/依赖文件。对应上游固定 commit，不照搬旧教程接口。
- 历史执行依据：源包 `evidence/local/scripts/` 中控制脚本、实验训练日志/filelist/config；脚本只能证明执行意图，需与日志和产物记录交叉核对。部署目录中的 `rvc_infer_file.py` 是历史 wrapper，不冒充官方仓库入口。
- 数量与时长依据：源包 `verification/remote-supplement.json` 和相关文档对 filelist 的交叉统计；旧首轮统计混入 `.spec.pt` 且标准库 wave 无法读 FLOAT WAV，以补核为准。
- 字节指纹依据：源包记载的模型/索引/基础资产核验结果，已在 [model-catalog](model-catalog/dependencies.json) 与[验证页](references/validation.md)注明为历史资料导入，不声称本模板新测模型字节。
- 本次实现验证：自造临时文件上的标准库 helper 单元测试。没有使用历史音频、加载权重或 FAISS 索引；没有新的训练/翻唱成品可链接。

## 权利与公开材料

仓库 MIT 仅覆盖本仓库适用代码与文本，不自动覆盖游戏角色、原始录音、配音表演、声音权益、歌曲、模型、HuBERT 特征或索引。`private_noncommercial_research` 是历史用途，不是授权；每次项目要登记权利主体、允许行为、用途、限制、依据和核验时间，未知项保持 `unknown`，不能继承“已通过”布尔值。

公开导出仅含方法、公共来源链接、必要参数、聚合统计、非敏感哈希与自有 helper。**不含 ASR 全文、权重、索引、音频、私有路径、机器信息、凭据或私人授权确认。** 本地运行的 filelist/spec/receipt 可能含绝对路径、台词标识或文件名，默认留在私有 job，另做字段白名单审核才能公开。索引包含语音内容特征，也不是可默认公开的“纯配置”。
