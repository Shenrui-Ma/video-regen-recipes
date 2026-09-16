# 验收范围与复测

## 已验证

- 剪辑规则来自作者提供的工程包与参数记录（C 类图→动态视频、D 类已有视频合集）；离线核对了示例 JSON 结构、参数边界与文档引用关系。
- 工作流依赖已固定：Toolkit revision `667eafddb9f42bb6c72ad27b665def9ada36df45` 与 `h3-i2v-live-portrait` 的 `api.template.json` SHA-256 记录在 [workflows/toolkit-source.json](../workflows/toolkit-source.json)。
- 离线复测（仓库根目录，需要 Pillow 与 FFmpeg/ffprobe）：

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s skills/character-showcase-editing/tests -v
python3 scripts/catalog.py check
```

## 未验证

- 未运行 H3 I2V 推理，未渲染、未播放、未做视觉检查；Toolkit 工作流只固定了版本与哈希，没有在本模板实跑。
- 没有已确认完备的 D 类独立工程可对照，D 类是通用方法而非某次历史工程的复刻。
- `runtime.clean_install_inference_verified=false`，`runtime.existing_environment_verified=false`。

## 使用者机器仍需完成

先跑通第一条片段的技术检查，再生成其余镜头并剪辑；核对首帧绑定、实际帧数、音轨与画幅，把本次实际使用的工作流版本与哈希写回用户项目记录。
