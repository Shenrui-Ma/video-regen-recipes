# 验收范围与复测

## 已验证

- 历史六段基础版（768×448 / 24fps / 1441 帧）在作者环境完成；参数、历史路线与素材来源见 [h3-runtime.md](h3-runtime.md) 与 [sources.md](../sources.md)。
- 工作流依赖已固定：Toolkit revision `eed34dbe95c55d29322401713952fccd4ae181ef` 与 `h3/ref2va-dialogue/api.template.json` 的 SHA-256 记录在 [workflows/toolkit-source.json](../workflows/toolkit-source.json)；本包保留对应的离线副本供构建器稳定使用，更新时先核对 commit 与哈希。
- 离线复测（仓库根目录）：

```bash
python3 -m unittest discover -s templates/anime-dialogue-scene/mygo-ave-mujica/tests -v
python3 scripts/catalog.py check
```

模板脚本只做校验与 API 图导出，不提交任务；`run_shot.py` 只在显式调用时提交单段。

## 未验证

- 本仓库重新参数化的脚本、示例与跨机器环境尚未首段实跑；Ave Mujica 示例的声音、身份与表演也需要重新验证。
- `runtime.clean_install_inference_verified=false`，`runtime.existing_environment_verified=false`。
- 未做本轮视觉、听感与字幕验收；六段与八段的路线参数不可混用。

## 使用者机器仍需完成

先跑完整第一段，核对身份一致性、对白音轨、字幕与解码帧数，再扩展余下段落；把本次实际使用的工作流版本、图哈希、Prompt ID 与成片哈希写回用户项目记录。
