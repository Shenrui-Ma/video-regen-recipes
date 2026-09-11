# 默认爻光素材

| 文件 | 用途 |
| --- | --- |
| [yaoguang.png](default/yaoguang.png) | 角色身份参考；2352×2352 |
| [driver.mp4](default/driver.mp4) | 原始动作与背景参考，保留其原有时间线 |
| [music.m4a](default/music.m4a) | 默认替换音乐，按成片时长截取并淡出 |
| [part-01.mp4](default/clips/part-01.mp4)、[part-02.mp4](default/clips/part-02.mp4) | 已发布的前两段，各158帧 |
| [part-03.mp4](default/clips/part-03.mp4)、[part-04.mp4](default/clips/part-04.mp4) | 后两段的 canonical 完整解码，各175帧 |

[manifest.json](default/manifest.json)记录实际文件大小、哈希和媒体规格。PNG 已去掉内嵌工作流、文字和 EXIF 元数据，压缩图像数据保持不变；媒体采用流拷贝移除容器元数据，剪辑片段另去掉了音频，统一使用独立音乐轨。

这些画面片段是默认剪辑的素材，不能代替 `latent.safetensors` 用于原生续接。模型权重、latent 和私人项目文件不随包分发。

素材由贡献者提供作为本案例输入和演示；仓库 MIT 许可不自动覆盖其中的角色 IP、原视频和歌曲，不附加第三方素材的商业使用或自由再分发授权。来源见[说明](../sources.md)。
