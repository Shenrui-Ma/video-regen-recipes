# 制作与导出契约

## 项目组织

```text
project/
  requirements.md        # 产品事实、观众、目标、交付与限制
  storyboard.json        # 镜头目的、证据、节拍
  timeline.json          # 编译后的帧时间线
  film.html              # 为当前产品编写的完整动画
  scripts/motion.js      # 如用骨架中的函数，复制此文件
  assets/                # 获准使用的图片、字体、声音
  assets.json            # 来源、用途、文件SHA256
  versions/v01/          # 每次独立输出，保留已接受版本
```

`examples/film.html` 在本仓库使用 `../scripts/motion.js`。若复制为项目根的 `film.html`，将其引用改为 `scripts/motion.js`；连同依赖一起交付。示例是一组信息卡与路径的12秒技术演示，不是任意产品都适用的广告。

当前 Python 需3.10+，渲染需Node.js、Playwright、独立Chromium和FFmpeg/ffprobe。先查已安装运行时，缺少时按用户环境准备依赖；无须 GSAP/Remotion/Manim。`CHROME_PATH` 可指定已有浏览器可执行文件，渲染器新建无登录上下文，不连接用户活动页。

## 单一叙事时钟

1. `setShotTime(t)` 必须接受任意有限非负秒数；大于结尾时保持最终状态。
2. 所有可见属性由时间计算。参考 `[9,1,9]` 的调用顺序，两个9秒应一致。
3. 浏览预览可由播放按钮启动rAF，但导出使用 `?render=1`，不得启动独立播放循环。隐藏预览控件，`#stage` 覆盖整个viewport。
4. DOM/字体/图片准备完成后再求几何；导出等待每次setShotTime完成并让浏览器完成绘制。若嵌入视频，函数返回在 `seeked` 和帧解码后才完成的Promise，并单独验证准确性。
5. 外部HTTP(S)请求在渲染器中被禁用。品牌字体、图标和截图使用本地资源，字体加载失败要修复，不静默依赖CDN。

旧工程采用实时录屏时需要测量实际启动前导，不能默认裁去两秒。新确定性逐帧方式没有启动前导；FFmpeg以 `i/fps` 采样的PNG序列编码。只控制JavaScript虚拟时间而让CSS过渡自然运行，会产生重复帧或不同步。

## 帧时间线

`plan.py` 接受 [分镜结构示例](../examples/storyboard.json)，只编译JSON，默认输出到标准输出：

```bash
python3 scripts/plan.py storyboard.json --output timeline.json
```

命令在复制的本模板目录执行时使用以上相对路径；在仓库根运行则加完整模板前缀。编译器不创建HTML、不生成语音或视频。

每镜写 `frames`、`overlap_out_frames`，节拍的 `[start_frame,end_frame)` 相对本镜。全局 `start[i+1]=start[i]+frames[i]-overlap[i]`；最后一镜不得留出转场，前后重叠不能吃掉中间镜头。最终 `duration=total_frames/fps`。编译器允许留白节拍，但留白必须服务阅读或叙事。

HTML读取或内嵌编译结果后按全局时间绘制场景。`file://` 下不依赖 fetch JSON；可由Agent将本次时间表安全序列化到内联脚本。内联文本中的 `</script>` 必须转义，不能把用户原文直接拼接成脚本。

## 导出与检查

```bash
node scripts/render-film.cjs examples/film.html output.mp4 1920 1080 12 30
```

此命令会实际渲染，只在制作视频时运行。渲染器：

- 等待图片解码、字体加载，记录JS与资源错误。
- 做前后跳转的PNG一致性检查；失败先检查独立时钟、字体和资源。浏览器抗锯齿也可能影响严格PNG比较，不能只删除检查冒充通过。
- 每帧检查可见的 `data-protected` 是否超出舞台或滚动溢出；检查可选 `data-mascot` 与保护区的矩形相交。父级透明度参与有效可见性判断。
- 逐帧PNG编码为 H.264、CRF18、yuv420p、SAR1，无声MP4；检查尺寸、fps、帧数并完整解码。
- 写入原HTML哈希、视频哈希、检查结果与 `.qc.json`，成功后无覆盖发布。锁和临时目录隔离，失败不产生成功报告。

输出最多4096×4096、120fps、18000帧且600秒内。逐帧PNG占用磁盘和时间；先完成脚本与布局检查，再正式渲染。目标文件系统需支持硬链接；崩溃遗留 `.lock` 时先确认对应进程已结束再清理。

DOM检查不是审美检查：它不检测所有文字相互遮挡、alpha形状、阴影、圆角、复杂遮罩或真实阅读难度。`uniqueFrames` 是诊断值，长时间稳定状态可以合理重复；不能只凭多张不同PNG证明动作正确。当前任务若仅要求文件检查，不运行上述媒体命令，记录实际跳过项。

## 声音与字幕

默认无声。网页中的WebAudio、video音轨不会自动进入PNG视频；需要的声音要显式合成。

- 旁白按真实音频长度放置，`line_start=scene_start+offset`。需要精确句间停顿时按采样率放到PCM时间线，不能从字数估时。
- 全片变速r时，画面时间、字幕和旁白起点都除以r，音频做对应atempo；优先优化分镜，避免用全局加速挤掉阅读时间。
- 字幕可预先在HTML由同一时钟显示，保护完整字幕框；后期叠字幕则必须把其真实边界也纳入画面检查。中文按像素宽度换行，英文按词换行。
- BGM增益依素材和旁白电平调整。共有剪辑Skill可为单视频添加BGM或混入已有原声；它不提供多句旁白自动布轨或字幕烧录，需要按本时间线实现对应合成步骤。
- 使用共有D模式添加音乐时，单段video的 `source_duration_seconds` 用实际导出时长；`layout.mode=plain`、`transition_frames=0`、`intro_frames=0`、`end_fade_frames=0`，防止再次加动画。多段拼接时同一边界只执行一次转场。

本地化需覆盖DOM、旁白、字幕和截图内文字四层；比例变更需重新排版和检查，而不只是改输出尺寸。
