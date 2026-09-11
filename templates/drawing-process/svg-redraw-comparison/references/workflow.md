# 纯 SVG 临摹到对比视频

## 环境

视频导出需要现有 Node.js、Playwright、Chromium/Chrome、FFmpeg/ffprobe。可选的轮廓辅助工具另需 Python 3.10+、Pillow、NumPy。生成的HTML本身不依赖这些库，打开时不联网、不调用Canvas。

`TEMPLATE_DIR` 指本模板目录，`PROJECT_DIR` 指用户项目。原图、SVG、HTML、视频分别保存，不在模板安装目录运行生成任务或覆盖已接受版本。

## 1. 清理参考

```bash
python3 "$TEMPLATE_DIR/scripts/clean_png.py" "$PROJECT_DIR/original.png" "$PROJECT_DIR/reference.png"
```

这是IDAT无损重压缩与元数据清理，不缩放像素。原图若含影响显示的方向或色彩配置，先检查转换；本示例已验证1536×1024的解码RGBA像素完全一致。

## 2. 两条明确区分的 SVG 制作方式

**大模型直接临摹：** 实际附加图片，使用[作者完整提示词](../prompts/author-original.prompt.txt)，输出内含原生SVG的完整HTML。随后逐项检查静态还原质量，并接好可控制时间的绘制流程。这条方式的实际效果需单独验证；提示词本身不保证高相似度。

**轮廓辅助：** 本例采用此方式，使用连续色域边界生成原生闭合路径。它不是位图嵌入，但存在颜色量化误差；必须披露方法。先根据本图制作 `regions.json`：

```json
{
  "reference_sha256": "干净参考图的完整SHA256",
  "width": 1536,
  "height": 1024,
  "regions": [
    {"id": "background", "polygon": []},
    {"id": "character-face", "polygon": [[100,100],[200,100],[200,200],[100,200]]}
  ]
}
```

区域坐标对应原图像素，后写区域覆盖之前区域；必须按真实人物、服装、脸部、环境等分区。上面坐标只是格式示意，不能直接用于参考图。[示例区域](../examples/regions.json)只适用于附带图片，工具用哈希拒绝错配。

```bash
python3 "$TEMPLATE_DIR/scripts/trace_reference.py" \
  --reference "$PROJECT_DIR/reference.png" --regions "$PROJECT_DIR/regions.json" \
  --output-dir "$PROJECT_DIR/vector-v1"
```

输出 `faithful.svg`、量化检查图与指标。先打开SVG并与原图比较，不以路径数量或文件大小证明质量。对本例的实际浏览器渲染，平均每通道绝对色差为1.3002/255、PSNR为42.6144dB，非零色差不能换算成“100%还原”。

## 3. 构建无 Canvas 的 Demo

轮廓辅助输出可使用：

```bash
python3 "$TEMPLATE_DIR/scripts/build_demo.py" \
  --reference "$PROJECT_DIR/reference.png" --regions "$PROJECT_DIR/regions.json" \
  --svg "$PROJECT_DIR/vector-v1/faithful.svg" --output "$PROJECT_DIR/demo.html"
```

参考图只在离线构建时用于提取线稿和底色。默认输出小于 200 KB 的 HTML、`redraw.svg` 和 `foundations.svg`；JS/CSS内联，完整矢量独立保存，不含位图或Canvas。双击HTML后选择两个SVG文件即可离线使用；通过本地HTTP服务打开则自动加载。加载器核对两个文件的SHA-256，不能混入其他示例。严格单文件交付时加 `--inline`，其HTML会明显更大。此构建器只接受本包轮廓格式，不是任意SVG的转换器。

默认40秒：构图0–2秒、线稿2–8秒、固有色8–14秒、阴影14–23秒、高光23–28秒、细节28–36秒、完成停留36–40秒。首次加载完成后显示完成图，点击播放从空白开始。

使用大模型自写HTML时应遵守同样的资源限制，并提供：

```javascript
window.replay = {
  duration: 40,
  renderAt(seconds) { /* 将本页SVG所有绘制状态确定地设置到该时刻 */ }
};
```

这里只定义接口，不能把空函数当作播放实现。若是CSS动画或SVG SMIL，适配它们的实际时间控制；不要改用Canvas。

## 4. 合成对比视频

```bash
node "$TEMPLATE_DIR/scripts/export_video.cjs" \
  --html "$PROJECT_DIR/demo.html" --reference "$PROJECT_DIR/reference.png" \
  --output "$PROJECT_DIR/comparison.mp4" --fps 24 --panel-width 768 --layout auto
```

已安装浏览器可用 `--browser` 指定其可执行文件。工具对原生SVG做DOM截图，再由FFmpeg独立合成原图；从不使用网页Canvas或在SVG里加入参考图片。输入横图时上下拼接，竖图时左右拼接；也可显式选择 `stacked` / `side-by-side`。

例子输出40秒、24fps、960帧、768×1024、静音H.264 MP4。导出采样为 `frame_index / fps`，不是实际录屏速度。加音乐另做后期，保留静音母版；不能让音乐长度截短绘制过程。

## 5. 验收与恢复

- 查开始、线稿、底色、细节、结束；页面中的原生矢量文件不包含位图。
- 同一时间点重复渲染结果一致；暂停、拖动、重置正常。
- 视频几何、解码帧数、FPS和完整解码通过；原图始终在上/左，绘制过程在下/右。
- 保留参考、SVG、HTML、视频哈希以及模型/辅助算法、参数与残余误差。
- 导出中断只重新导出，SVG重做才重新构建HTML。禁止用上一版粗稿视频充当新版结果。

文件较大属于高密度矢量示例的代价；不要为了减少文件大小悄悄改成位图或丢失细节。
