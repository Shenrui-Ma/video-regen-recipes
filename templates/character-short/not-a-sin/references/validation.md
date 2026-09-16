# 验收范围与复测

## 已验证

- 历史《XX不是罪过》案例在作者环境完成：RIFE 半速参考、本地 H3 串行音视频续接、原速恢复与音乐回装；帧账与时间线见 [evidence/timeline.json](../evidence/timeline.json) 与 [evidence/README.md](../evidence/README.md)。
- 离线检查：时间线 JSON 结构、示例提示词与文档引用关系可解析。

## 未验证

- **没有可直接导入的续接执行包**：H3 CLI 与联合 AV Motion Context 适配代码尚未打包、未锁定版本、未在干净环境验证；普通 Ref2VA 图不能替代它。缺项清单见 [workflows/README.md](../workflows/README.md)。
- 新角色完整复现仍为 `new_character_validation: pending`；干净安装、视觉与听感验收均未完成。
- `runtime.existing_environment_verified=true` 只表示历史案例在作者环境下完成，不代表本目录能一键复现；`runtime.clean_install_inference_verified=false`。

## 使用者机器仍需完成

先准备角色图与经核对的半速驱动参考（参考视频可按[参考视频获取 Skill](../../../../skills/reference-video-fetch/SKILL.md)取到本机），再按帧账完成首段与一次真实续接段；分别记录源输入、有效参考、采样、发布四种帧数，确认身份、动作、接缝与音轨后再扩展全片。
