# 项目封面

`hero.png` 为本项目生成的 AI 概念插画（2172 × 724），非 H3 实测样片。

使用内置 image_gen 工具生成，提示词见 [hero-prompt.txt](hero-prompt.txt)。本图采用 [MIT License](../LICENSE)。

`icons/` 中的 Bilibili 与 Rednote 图标来自 [Simple Icons](https://github.com/simple-icons/simple-icons)，图形采用 [CC0](https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md)，品牌标识归各自权利人所有。

## 成片片段

`showcase/` 存放首页那一排循环 GIF，取自已发布成片：MyGO 番剧、STARBOY 高松灯、一点一滴刺痛我的心（爻光）、星穹铁道 泳池派对。四张统一 180 × 270、2:3、12.5 fps，单张 1–2 MB，各 63 帧左右（约 5 秒）。

片段按同一画幅比例取景：原片为 1:1 构图时先取中间方块再裁到 2:3，其余按人物所在区域裁切。四张全部原速，不做变速。

爻光那张源片为 1728 × 2304 竖屏 3:4，取 `crop=1536:2304:96:0`，从 0 秒起原速截 5 秒，63 帧覆盖 0–4.96 秒。泳池派对那张源片为 1080 × 1920 竖屏，取 `crop=1080:1620:0:130`，从 36.35 秒起截 5 秒：源片在 41.44 秒处有一次约 0.2 秒的溶解转场，严格从 37.5 秒起取满 5 秒会把这处转场剪进循环，因此起点前移 1.15 秒以避开转场。四张都只保留构图稳定的一整段镜头，循环时不会出现切镜或模糊闪动。片段只作展示，完整作品链接见首页；角色 IP、音乐与第三方素材权利仍归各自权利人，本仓库 MIT 许可不覆盖这些内容。

Civitai 图标取自其[官方仓库图标](https://github.com/civitai/civitai/blob/main/public/favicon-blue.ico)，品牌标识归 Civitai 所有。
