# 0.3.0 模板修订

- 增加可选RMBG工作流、模型来源和人物alpha转纯色RGB的操作入口；保留原图、mask、输出SHA，不把去背景设为所有任务的强制依赖。
- 补充实际FFmpeg AAC预检和已生成片段的后处理恢复，避免在GPU采样之后才发现编码器不兼容；成片必须通过验证后发布。
- 默认分发包去掉图片、音乐、视频和权重，只提供知识、代码、工作流、许可与获取清单。用户参考图优先，历史示例角色按需获取。
- 同步入口、安装、运行、许可及来源说明；记录既有环境真实首段结果与干净安装/完整续接尚未验证的边界。

本版没有重新生成视频或更改先前成片。具体测试及打包验收见 [package-verification.json](package-verification.json)，既有真实GPU结果见 [first-segment-validation.json](first-segment-validation.json)。
