# 来源与验证

## 成品与整理

成品、后期实践和本仓库整理：**四倍体果蝇 / Shenrui Ma**。

- [𝑺𝑻𝑨𝑹𝑩𝑶𝒀 高松灯](https://www.bilibili.com/video/BV1BPgq6hEey/)
- [𝑩𝒊𝒍𝒍𝒊𝒆 𝑱𝒆𝒂𝒏 —— 千早爱音](https://www.bilibili.com/video/BV1dQKY6ME3t/)

参考资料为作者提供的《少女乐队 SVC 翻唱 保姆级溯源资料包 v1.0》，构建日期 2026-09-12。ZIP SHA-256：`4b61950d9427e6e242384397486467796c297c2c244c43a771be857520c04864`。本次实算相符，284 个清单文件全部通过核对；私有包、原曲、模型、成片和机器配置不随模板发布。

资料包 `post/postproduction-and-pitfalls.md` 第 6 节与 `docs/01_完整操作手册.md` 第 10 节提供母带冻结、字幕时间轴和独立可视化的依据。历史记录是双律动线成片；部分原渲染脚本和 cue 缺失。因此这里的环形几何和能量包络是**新的独立实现**，不是找回了原 MV 的精确配方。

## 模型和素材归属

此模板本身不调用模型。参考成品的歌声音色来自少女乐队 DDSP 模型，感谢模型作者**路边墨缇斯**；[原分享/教程入口](https://www.bilibili.com/video/BV1JU2LBZEt5/)，详细模型、声码器与许可见[翻唱模板来源](../../singing-cover/girls-band-ddsp/sources.md)。不能把这份致谢当作原曲、录音、角色、声优或字体授权。

本仓库原创渲染代码依仓库 MIT 许可；[Pillow](https://python-pillow.github.io/) 与 [FFmpeg](https://ffmpeg.org/) 依各自许可。用户图片、字体、歌词、原曲和录音不转授 MIT。发布生成内容前单独核对使用权。

## 可复查的验证

2026-09-12，macOS：使用自制 PCM16 双声道测试音频（含静音、100 Hz 与反相声道）和几何测试图，不使用商业歌曲或模型权重。测试包括母带错配与中途替换、参数/字幕越界、禁止覆盖、编码异常退出、短音轨/延迟起点、静音/底噪、反相声道能量、字幕边界、文字适配，以及横竖屏真实 FFmpeg 编码、帧数/时长/音轨和完整解码。

另实跑 1080×1920 与 1920×1080 的 60 fps、3 秒合成短片，各 180 帧；抽查安静段、强音和字幕切换帧，确认环不侵入标题/字幕区。此结果只证明测试素材上的运行与布局，不代表真实角色图已验收。

```bash
python3 -m unittest discover -s templates/music-visualizer/rhythm-ring/tests -v
```

需要 Pillow、FFmpeg、ffprobe 与本地测试字体；无系统字体时可设 `TEST_FONT`。缺工具时测试会明确跳过，不能当作渲染成功。未运行 GPU 推理、整曲复刻、Windows/Linux 原生渲染或人工歌曲听感验收。
