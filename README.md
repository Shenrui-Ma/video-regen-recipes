# Video ReGen Recipes

**把喜欢的视频，创作成你的版本。**

![Video ReGen Recipes 概念片场](assets/hero.png)

<sub>AI 概念插画，非 H3 实测样片。[图像说明](assets/README.md)</sub>

收集二次元二创与番剧的制作模板，让 Agent 帮你准备角色图像和声音、设计分镜、生成视频并完成剪辑。你可以替换角色，修改场景、台词和画风，做出自己的版本。

**建设中：首批模板正在整理，暂未提供可运行的模板或 Skill。**

## 制作范围

- **视频**：在本机或自行管理的 GPU 服务器上运行 ComfyUI + MiniMax H3。
- **图片与声音**：本地或在线工具均可，如 ComfyUI、NovelAI、GPT Image、语音服务和已有素材。

制作流程：**选模板 → 准备素材 → 分镜 → H3 生成 → 剪辑成片**。

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
