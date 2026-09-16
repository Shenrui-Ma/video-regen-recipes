# 验收范围与复测

## 已验证

- 历史 8 段案例（约 62 秒竖屏合集）在作者既有环境完成：首帧由 ComfyUI 生成，片段由本地 H3 I2V 生成并保留自然声，节奏与替换方法见 [shot-plan.md](shot-plan.md)、参数见 [generation.md](generation.md)。
- 离线核对了请求示例、8 段镜头计划与剪辑配置的结构，以及共用剪辑 Skill 的离线测试。
- 工作流依赖已固定：Toolkit revision `667eafddb9f42bb6c72ad27b665def9ada36df45` 与 `h3-i2v-live-portrait` 的 `api.template.json` SHA-256 记录在 [workflows/toolkit-source.json](../workflows/toolkit-source.json)。

## 未验证

- 未用新角色重跑 8 段链路；未做视觉与听感验收；干净安装未验证。
- `runtime.clean_install_inference_verified=false`；`runtime.existing_environment_verified=true` 仅指历史案例在作者环境下完成。

## 使用者机器仍需完成

逐镜头绑定首帧 → 生成 → 保留自然声 → 按 8 段节奏剪辑；人工确认角色一致性、表情与手部、原声与 BGM 混音，以及跨段接缝。断线时先查询原任务再决定是否重投。
