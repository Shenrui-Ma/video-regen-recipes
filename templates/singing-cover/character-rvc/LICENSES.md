# 许可与第三方资源

本模板原创文档、helper 脚本与示例配置沿用仓库的 [MIT License](LICENSE)。这项许可**不**覆盖下列任一项：

- **RVC 官方实现**（[RVC-Project，固定 commit 4338f12](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/tree/4338f12c3c28c80b3ac015e2d0df66c41592746d)）：代码 MIT，不覆盖全部权重与录音。
- **HF HuBERT / RMVPE / v2 预训练权重与索引**（[VoiceConversionWebUI 资产入口](https://huggingface.co/lj1995/VoiceConversionWebUI/tree/main)）：`main` 可变，历史下载 revision 未恢复；逐项许可需自行核对，期望字节见 [model-catalog/dependencies.json](model-catalog/dependencies.json)。
- **pymss 与分离模型**：pymss 代码 MIT；其部署镜像卡片的许可不自动证明原作者授予再许可。只复用分离/声部听审方法。
- **角色、录音与声音权益**：历史来源为[【明日方舟中文语音】莫斯提马（CV. 若舞）](https://www.bilibili.com/video/BV17a411d7ex/)的转载合集，角色与游戏权利见[明日方舟官方站](https://ak.hypergryph.com/)。**不把若舞列为本合成演唱的参与者或背书人**；合成歌曲应披露 AI 音色转换。
- **歌曲、歌词与伴奏**：归各自权利人；本模板不附带任何音频。
- **工具**：[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[FFmpeg](https://ffmpeg.org/) 依各自许可。

身份来源的 `private_noncommercial_research` 是历史用途记录，**不是授权**。每个项目都要登记权利主体、允许行为、用途、限制、依据与核验时间，未知项保持 `unknown`，不能继承“已通过”。

公开导出不含 ASR 全文、权重、索引、音频、私有路径、机器信息、凭据或私人授权确认；索引含语音内容特征，也不是可默认公开的配置。
