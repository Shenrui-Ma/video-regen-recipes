# 示例使用

- `request.example.json`：把一句话记录成角色、场景与输出要求。默认原创成年角色，可替换成用户指定角色。
- `eight-shot-plan.json`：8 张首帧、各段 H3 参数、动作及剪辑区间。这里的种子为 `null`，实际调用前逐段生成一次并固定保存。
- `edit.json`：可直接给公共剪辑工具使用的 8 段配置，默认保留自然声。
- `edit-with-bgm.json`：相同剪辑计划，再混入用户音乐，BGM -12dB。

路径相对配置所在用户项目，示例源时长来自历史源文件。

把所需 JSON 复制至用户项目后修改。新生成的源视频必须用实际视频流时长更新 `source_duration_seconds`，并确认裁切终点不越界；不能为了通过计划检查而把缺少的帧数写成历史值。`eight-shot-plan.json` 是 Agent 规划输入，不直接交给 ComfyUI 或后期渲染器。

从仓库根运行以下命令只校验数据和打印剪辑计划，不读取媒体、不渲染：

```bash
python3 skills/character-showcase-editing/scripts/showcase.py \
  templates/character-showcase/swimsuit-live-portraits/examples/edit.json --plan
```

实际项目中把 `clips/01.mp4` 至 `clips/08.mp4` 替换成准备好的文件。有配乐时选 `edit-with-bgm.json`，同时填写 `audio/music.m4a`；默认 `edit.json` 不需要配乐文件。编辑器的 `--check` 只做文件存在性等检查；`--render` 才会执行渲染，参见[公共 Skill](../../../../skills/character-showcase-editing/SKILL.md)。

示例不自带成片、图片或 BGM，不会复用私人素材完成“新角色生成”。
