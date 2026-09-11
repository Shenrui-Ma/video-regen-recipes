# 从参考图到对比视频

## 环境与文件

需要 Python 3.10+、Node.js、可用的 Playwright＋Chromium，以及带 libx264 的 FFmpeg/ffprobe。优先使用宿主已有环境；没有 Chromium 时可用导出器 `--browser` 指向已安装的 Chromium/Chrome。这里不需要 H3、ComfyUI 或图片生成 API。

模型负责生成矢量图，浏览器负责重放，FFmpeg负责编码。以下设置 `TEMPLATE_DIR` 为本模板目录，`PROJECT_DIR` 为用户项目目录，所有输出用新文件名。

```text
project/
├── original.png         # 用户原文件，不覆盖
├── reference.png        # 无损重编码、去元数据的输入
├── redraw.svg           # 本图的矢量重绘
├── demo.html            # 自包含播放器
└── comparison.mp4       # 视频交付
```

## 1. 清理参考图

```bash
python3 "$TEMPLATE_DIR/scripts/clean_png.py" "$PROJECT_DIR/original.png" "$PROJECT_DIR/reference.png"
```

工具重压缩PNG的IDAT数据，保留必要的图像/调色板/透明信息，移除可选元数据；不调整大小或重画像素。输入若有影响显示的色彩配置或方向信息，先检查清理前后显示与解码像素，不能直接假定外观不变。附带参考已通过RGBA逐像素一致性验证。

## 2. 让大模型写SVG

实际附加 `reference.png`，使用[提示词](../prompts/redraw.prompt.txt)，把结果保存为 `redraw.svg`。先检查最终构图，再检查分阶段结构。不要上传自己的环境配置，也不要把原图文件名写进公开提示词。

默认例子的 SVG 是简化的流程演示，用于测试图形播放与导出，不能作为新图的通用人物或高相似度承诺。

## 3. 生成可播放网页

```bash
python3 "$TEMPLATE_DIR/scripts/build_demo.py" \
  --reference "$PROJECT_DIR/reference.png" --svg "$PROJECT_DIR/redraw.svg" \
  --output "$PROJECT_DIR/demo.html" --layout auto --panel-width 768 \
  --lead-seconds 1 --draw-seconds 24 --hold-seconds 3
```

`auto` 对横图使用上下、对竖图使用左右。可以显式选 `stacked` 或 `side-by-side`。原图和SVG需相同比例，完整显示，不通过拉伸或裁切制造相似。

输出是自包含HTML，下载后可离线打开。画面标签在图像外，播放栏不会进入导出视频。总时长为开场等待＋绘制＋结尾停留。例子为1＋12＋3＝16秒；上方原图1536×1024按比例显示为768×512，下方相同，加两条32像素标签栏后输出768×1088。

阶段比例：起稿0–13%、线稿10–34%、铺色34–66%、明暗66–84%、细节84–100%。这是可解释的绘制步骤重放，不是实际大模型生成代码的耗时记录。阶段内部按独立图形推进；线条和颜色是不同显现方式。

## 4. 导出MP4

在具备 Playwright 的 Node 环境运行：

```bash
node "$TEMPLATE_DIR/scripts/export_video.cjs" \
  --html "$PROJECT_DIR/demo.html" --output "$PROJECT_DIR/comparison.mp4" --fps 30
```

需要指定现有浏览器时加 `--browser` 和其可执行文件路径；FFmpeg不在PATH时可加 `--ffmpeg` / `--ffprobe`。这些路径只放在用户运行环境，不写进模板。

只打开本工具构建并检查过的HTML，不运行来源不明的网页代码。每帧固定取 `frame_index / fps`，共 `ceil(duration × fps)` 帧；结尾停留确保完整图被记录。导出器不会播放网页控制栏或依赖屏幕录制速度。

输出为静音H.264 MP4。若要音乐，另做音频合成并保留静音母版；避免因音乐长度自动截短视频。

## 5. 验收与复用

至少查看空白起点、线稿、铺色、最终四个时刻，确认原图面板始终不变、绘图区不是位图覆盖，且正向播放和拖动到同一时刻得到同样画面。校验输出帧数、分辨率、FPS并完整解码。

```bash
ffprobe -v error -count_frames -show_streams -show_format -of json "$PROJECT_DIR/comparison.mp4"
ffmpeg -v error -xerror -i "$PROJECT_DIR/comparison.mp4" -map 0:v:0 -f null -
```

保存参考图/最终SVG/HTML/视频的SHA-256、模型和提示词、排版、时长与帧率。图像还原质量与导出管线分开验收；修改矢量细节只需重新构建和导出，不重新准备原图。

## 维护检查

在模板目录运行 `python3 -m unittest discover -s tests -q`。已配置Playwright时运行 `node tests/check_player.cjs`；需要现有浏览器可设置 `CHROMIUM_EXECUTABLE`。这些检查不调用绘图模型。
