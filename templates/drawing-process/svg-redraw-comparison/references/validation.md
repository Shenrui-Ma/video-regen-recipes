# 验收范围与复测

## 已验证

- 示例已在本机渲染：静态 SVG 平均每通道色差 **1.30/255**，纯 SVG 播放、对照 MP4 与打包流程通过；见 [examples/validation.json](../examples/validation.json) 与 [assets/manifest.json](../assets/manifest.json)。
- 产物为原生 SVG（无 Canvas、无位图嵌入、无外链），这是硬约束而非建议。
- 离线复测（仓库根目录；需要 Pillow、FFmpeg/ffprobe、Node 与可用的无头浏览器）：

```bash
python3 -m unittest discover -s templates/drawing-process/svg-redraw-comparison/tests -v
node templates/drawing-process/svg-redraw-comparison/tests/check_player.cjs
python3 scripts/catalog.py check
```

## 未验证

- 新参考图的还原精度仍需人工复核；存在调色板量化误差，**不构成逐像素 1:1** 的结论。
- 未在干净环境重跑；Windows 未验证；`runtime.clean_install_inference_verified=false`。
- `runtime.existing_environment_verified=true` 指示例在本机完成渲染，不代表新图已验收。

## 使用者机器仍需完成

对新的参考图重跑轮廓与区域分析，人工比较静态 SVG 与原图；确认对照 MP4 的帧数、时长与完整解码后再交付。
