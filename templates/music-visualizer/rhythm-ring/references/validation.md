# 验收范围与复测

## 已验证

- 2026-09-12 在 macOS 上用自制 PCM16 双声道测试音频（含静音、100 Hz 与反相声道）与几何测试图实跑：母带错配与中途替换、参数/字幕越界、禁止覆盖、编码异常退出、短音轨与延迟起点、反相声道能量、字幕边界与文字适配。
- 实跑 1080×1920 与 1920×1080 的 60 fps、3 秒合成短片（各 180 帧），抽查安静段、强音与字幕切换帧，确认环不侵入标题与字幕区。
- 离线复测（需要 Pillow、FFmpeg/ffprobe，可选 `TEST_FONT`）：

```bash
python3 -m unittest discover -s templates/music-visualizer/rhythm-ring/tests -v
python3 scripts/catalog.py check
```

## 未验证

- 未使用真实歌曲、真实角色图或模型权重；未复刻历史双律动线 MV 的精确配方（环形几何与能量包络是新的独立实现）。
- 未做整曲复刻、听感验收、GPU 翻唱、Windows/Linux 原生渲染。
- `runtime.existing_environment_verified=true` 只指上述合成素材的渲染；`runtime.clean_install_inference_verified=false`。

## 使用者机器仍需完成

绑定自己的母带与图片 → 渲染 → 人工看头尾、强拍与字幕切换帧，听人声截断、漂移与爆音；字体缺字与角色遮挡不能靠 ffprobe 发现，须人工确认后把 `visual_review` 从 `not_performed` 改成实际结论。
