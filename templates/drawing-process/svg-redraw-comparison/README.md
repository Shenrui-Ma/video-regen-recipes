# 基于大模型的SVG临摹重绘

**给一张图，制作“原图对照＋从空白到完成的 SVG 绘制过程”视频。**

> “把这张图临摹成 SVG，按起稿、线稿、铺色、明暗、细节展示过程，并导出对比视频。”

横图默认**上方原图、下方绘制过程**；竖图默认左侧原图、右侧绘制过程，也可手动选择排版。

## 怎么用

让 Agent 读取 [SKILL.md](SKILL.md)，提供图片和想要的视频时长。它会完成参考图处理、SVG 临摹、分阶段播放和视频导出，不停在输出 SVG 代码。

**参考图 → 大模型编写分层 SVG → 播放 Demo → 逐帧导出 → MP4。**

不需要 ComfyUI 或视频生成模型。使用浏览器渲染矢量绘制过程，画面时间由导出器确定。

## 示例与工具

- [对比视频](examples/preview.mp4)：上下布局，16秒、30fps。
- [可播放 Demo](examples/demo.html)：下载后用浏览器打开，可播放、暂停、拖动与重置。
- [SVG 示例](examples/redraw.svg) · [参考图](assets/reference.png) · [制作步骤](references/workflow.md)

附带 SVG 是用于演示播放与导出链路的简化矢量稿，不是高精度还原评测。绘制过程是按图形和阶段重放，并非模型思考过程录屏。

模板实现：**Shenrui Ma（四倍体果蝇）**。灵感来源：[Hope麻匪《再给 GPT6 Astra 一点时间》](https://www.bilibili.com/video/BV1azYW6zEXy)。[来源与验证](sources.md)
