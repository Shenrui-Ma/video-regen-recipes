# 验收范围与复测

## 已验证

- 2026-09-11 整理时核对：归档完整性、JSON 与 Python 结构、两套剪辑方案（缩放模糊版 / 静态溶解版）的参数与时间线。
- 离线复测（仓库根目录，需要 Pillow 与 FFmpeg/ffprobe；缺工具时测试会明确跳过）：

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/character-showcase-editing/tests -v
python3 scripts/catalog.py check
```

## 未验证

- 未在干净环境运行 ComfyUI 生图，未渲染新环境成片，未做视觉检查，未重看历史素材。
- `runtime.clean_install_inference_verified=false`，`runtime.existing_environment_verified=false`。

## 使用者机器仍需完成

用实际角色与主题跑通一次“生图 → 剪辑”全链路，人工确认身份一致性、构图、转场与配乐；保留实际参数、输入输出哈希与成片。图片合集不调用视频模型，因此不需要 GPU 推理。
