# Video ReGen Recipes

**把喜欢的视频，创作成你的版本。**

![Video ReGen Recipes 概念片场](assets/hero.png)

<sub>AI 概念插画，非 H3 实测样片。[图像说明](assets/README.md)</sub>

收集二次元二创与番剧的制作模板，让 Agent 帮你准备角色图像和声音、设计分镜、生成视频并完成剪辑。你可以替换角色，修改场景、台词和画风，做出自己的版本。

**首份原创二创配方已收录：[XX不是罪过 · 本地 H3 角色重演](templates/character-short/not-a-sin/)。** 银狼案例已有历史成片，公开版提供制作指南、提示词、参数与证据；完整执行工作流和可安装 Skill 仍在整理中。

## 制作范围

- **视频**：在本机或自行管理的 GPU 服务器上运行 ComfyUI + MiniMax H3。
- **图片与声音**：本地或在线工具均可，如 ComfyUI、NovelAI、GPT Image、语音服务和已有素材。

制作流程：**选模板 → 准备素材 → 分镜 → H3 生成 → 剪辑成片**。

## 第一份配方：XX不是罪过

由 **Shenrui Ma** 在《银狼不是罪过》的多轮制作中迭代形成。以已有动作／音乐梗为启发，采用 **RIFE 半速参考 → 本地 H3 整链续接 → 恢复原速 → 原音乐回装**，可选补帧与超分。

它不是只替换一个角色名的提示词，也不是原作者 Seedance 路线的原样复刻。适合希望保留参考动作与剪辑节奏、用自己角色重新表演的创作者。

[阅读完整配方](templates/character-short/not-a-sin/) · [历史成片证据与限制](templates/character-short/not-a-sin/evidence/) · [来源与署名](templates/character-short/not-a-sin/sources.md)

## 模板方向

- [番剧对白与叙事场景](templates/anime-dialogue-scene/)
- [角色主题短片](templates/character-short/)
- [液态形变与风格化 ED](templates/liquid-morphing-ed/)

## 参与整理

```bash
git clone https://github.com/Shenrui-Ma/video-regen-recipes.git
cd video-regen-recipes
```

欢迎分享视频案例、提示词、工作流和复现经验，见 [贡献指南](CONTRIBUTING.md)。

[模板怎么写](docs/template-format.md) · [本地 H3](docs/local-h3.md) · [图片与声音](docs/assets-and-audio.md)

## 许可

原创代码与文档采用 [MIT License](LICENSE)。模型和第三方素材遵循各自许可。
