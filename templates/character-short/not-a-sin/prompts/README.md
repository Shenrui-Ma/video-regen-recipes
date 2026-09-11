# 提示词

使用 [ref2va.template.txt](ref2va.template.txt) 填写以下变量。这是角色可替换的通用稿，尚未重新运行验证。

| 变量 | 填写内容 |
| --- | --- |
| `CHARACTER_DESCRIPTION` | 角色图中可见的身份与外观特征 |
| `OUTFIT_DESCRIPTION` | 本次固定服装与配饰，不照搬源片换装标签 |
| `BACKGROUND_ANCHORS` | 当前参考的背景配色、亮度、文字与构图 |
| `VISIBLE_FRAMES` / `DURATION_SECONDS` | 当前**慢速子段**发布后的帧数／时长，不含隐藏前缀 |

`<Subject 1>` 用于角色身份参考，不是严格首帧；`<Video 1>` 提供当前动作与切镜。图像、视频、音频分别编号，核对实际输入顺序。无音频连线时，删除 `<Audio 1>` 定义、对应 retention 项及 summary 中的 audio reference。

提交前检查无残留 `{{...}}`、旧人名、旧时长或错误服装，保存实际提交文字。相同提示词与 Seed 不保证跨环境像素一致。

## 历史稿修正

- **时长**：原稿沿用 175 帧／7.291667 秒，对 177 帧慢速子段不适用；通用稿改为逐段填写。
- **保留策略**：自写的 `fully_preserved_except_main_performer` 改为 `partially_preserved`，另述换角目标。
- **背景与音乐**：背景锁定措辞只是软提示；`[audio reuse]`／`fully_copy` 也不保证音轨复制。通用稿按实际绑定使用 `[audio reference]`，最终音乐由后期回装。
