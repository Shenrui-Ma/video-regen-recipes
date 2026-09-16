# MyGO / Ave Mujica AI 番剧

原创模板：**Shenrui Ma（四倍体果蝇）**。

**从一句剧情想法开始，制作约一分钟、有角色对白和字幕的同人短篇。**

示例：[AI 少女乐队番剧（B站）](https://www.bilibili.com/video/BV1WhY364ECX)。提示词无任何指导，单次抽卡，有瑕疵。

默认六段、768×448、24fps。H3 根据角色图、场景图和音色参考，逐段联合生成视频与新对白，再拼接、校对字幕。图片可用 ComfyUI、GPT Image 2 或 NovelAI；视频默认使用本地 ComfyUI。

> 提供两份原创剧情示例、参数化 API 图、构建与单段运行工具。制作链路来自已有 MyGO 记录；公开版完成离线检查，尚未在新环境跑通。Ave Mujica 是待验证扩展，不附带角色素材或模型权重。

## 从这里开始

让 Agent 读取 [SKILL.md](SKILL.md)，然后告诉它：

> 用这份模板制作一集 MyGO（或 Ave Mujica）短篇。剧情是：……。保持角色服装一致，使用日语对白和中日双语字幕。先完成素材与第一段验收，再继续全片。

也可以手动按下列顺序操作：

| 步骤 | 做什么 | 完成后应有 |
| --- | --- | --- |
| 1 | [选剧情、拆六段](references/story-and-shots.md) | `episode.json`，角色、对白和镜头明确 |
| 2 | [准备角色图、场景和声音](references/assets-and-voices.md) | 实际素材、来源与哈希，每段绑定表 |
| 3 | [检查 H3、导出工作流](references/h3-runtime.md) | 本次 API 图、提示词、输入映射 |
| 4 | [生成并验收第一段](references/running-shots.md) | 可播放、有正确对白的基础片段 |
| 5 | 逐段生成；只返修失败项 | 六段已验收原片及版本清单 |
| 6 | [拼接、字幕、音乐与交付](references/editing-and-delivery.md) | 原速母版、字幕文件和成片 |

## 两份起步示例

- [MyGO：排练前的便签](examples/episode.mygo.json)：一次小误会到共同排练，五位角色分段出场。
- [Ave Mujica：开场前的暗号](examples/episode.ave-mujica.json)：后台准备与开演前的默契，不复述官方剧情。

示例是待填写素材和模型的制作计划，不能直接提交到 ComfyUI。对白为本仓库新写的同人示例，不是官方台词。

## 默认先做好这些

- 每段只安排一个主要动作和少量对白；不要求每镜五人同时出现。
- 先复用角色、服装、场景与音色资产，默认一段一段生成。
- 串行运行便于控制资源；本模板的片段彼此独立，**没有跨段 latent 续接**。
- 第一段通过后再扩展；高清、复杂走位、配乐、修脸与超分按需增加，见[效率与进阶](references/efficiency-and-variants.md)。

[来源与许可](sources.md) · [验证状态](evidence/README.md)

## 配套资源

- [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)：`h3/ref2va-dialogue` 工作流，固定 revision 与文件哈希见 [workflows/toolkit-source.json](workflows/toolkit-source.json)
- [Shenrui-Ma/video-regen-assets](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets)：公开素材库；角色图与音色按用户自己的来源准备

第三方组件、角色 IP 与声音权利见 [LICENSES.md](LICENSES.md)，本次验证范围见 [验证记录](references/validation.md)。
