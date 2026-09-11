# 基于大模型的SVG临摹重绘

**给一张图，制作“原图对照＋完整 SVG 绘制过程”视频。**

> “按这张图做 SVG 临摹，从构图、线稿、固有色到阴影、高光与细节，最后导出对比视频。”

横图默认**上方原图、下方绘制过程**；竖图默认左右对比。纯 SVG Demo 不嵌入原图，参考面板仅在视频合成时加入。

## 怎么用

让 Agent 读取 [SKILL.md](SKILL.md)，提供参考图和视频要求。交付包括 SVG、可播放网页和 MP4，不能只交网页就结束。

**参考图 → SVG 临摹与质量检查 → 纯 SVG 绘制 Demo → 逐帧截图 → 视频合成。**

不使用 Canvas，不需要 ComfyUI 或视频推理模型。网页不包含位图或 Base64 图片，脚本与样式内联；轻量示例单独加载本地 SVG 数据，无需联网。

## 实际示例

- [对比视频](examples/preview.mp4)：40秒、24fps，上原图、下绘制过程。
- [轻量 SVG Demo](examples/demo.html)：HTML 小于 200 KB；下载后打开，按页面提示选择同目录的 `redraw.svg` 与 `foundations.svg`，即可离线播放、暂停、拖动或查看完成图。
- [独立 SVG](examples/redraw.svg) · [完整提示词](prompts/author-original.prompt.txt) · [操作步骤](references/workflow.md)

轻量化保留全部路径与绘制阶段：完整 SVG 约 16.34 MB，阶段数据 [foundations.svg](examples/foundations.svg) 约 0.61 MB。缩小的是 HTML 并消除重复内嵌，不是降低画面精度。通过本地 HTTP 服务打开可自动加载两个文件。

本例采用连续色域轮廓矢量化及语义分层，静态SVG平均每通道色差为1.30/255，视觉接近原图，但并非严格逐像素1:1。它不是大模型逐笔手工绘画或思考过程录像。

模板实现：**Shenrui Ma（四倍体果蝇）**。灵感来源：[Hope麻匪《再给 GPT6 Astra 一点时间》](https://www.bilibili.com/video/BV1azYW6zEXy)。[来源与验证](sources.md)
