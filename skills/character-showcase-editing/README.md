# 角色合集剪辑器

同一个脚本处理图片合集、原图转动态视频和视频合集。准备素材的完整链路由上层模板编排；这里接受生成后锁定的文件清单。

复制 [A 动态图片](examples/a-dynamic-images.json)、[B 静态图片](examples/b-static-images.json)、[C 图视频混剪](examples/c-still-video.json) 或 [D 视频合集](examples/d-video-collection.json) 到新项目，再替换相对路径。示例不包含实际媒体。

```bash
# 在仓库根目录运行；计划无需 Pillow 或 FFmpeg：
python3 skills/character-showcase-editing/scripts/showcase.py job/edit.json --plan
python3 skills/character-showcase-editing/scripts/showcase.py job/edit.json --check

# 实际渲染需要当前 Python 可导入 Pillow，且 PATH 包含 ffmpeg、ffprobe：
python3 skills/character-showcase-editing/scripts/showcase.py job/edit.json --render
```

省略开关等于 `--plan`。计划结果写到标准输出，不写媒体或成功记录。`--check` 只读取 JSON 并确认素材路径存在；即使通过，也不等于文件能被解码。缺少环境或输入时明确失败，不自动安装软件、下载模型或发起推理。

## 配置

| 字段 | 默认 / 含义 |
| --- | --- |
| `schema_version` | 必填 `1` |
| `mode` | 必填 `A` / `B` / `C` / `D` |
| `output` | 必填新 `.mp4` 路径；相对当前 JSON |
| `canvas` | `{width:1080,height:1920,fps:60}`，尺寸为偶数，fps 为整数 |
| `clips` | 必填显式有序清单，1–64 段，不做目录扫描排序 |
| `total_frames` | A/B 必填；C/D 禁止填写，防止固定总长与重叠减时矛盾 |
| `transition_frames` | A/B 默认 `round(25×fps/60)`；C/D 默认 `round(30×fps/60)`；B/C/D 可设 `0` 硬切 |
| `intro_frames` | B 默认 `round(50×fps/60)` 从黑入场；其他为 `0` |
| `intro_blur_frames` | 默认 `0`；设置后在整片开头将 sigma 30 模糊副本线性混合到运动中的清晰画面 |
| `end_fade_frames` | A 默认 1 秒，B 默认无，C/D 默认 0.5 秒；均在既定时长内淡出 |
| `layout.mode` | A/B/C 默认 `blurred`，D 默认 `plain`；另支持 `blurred-fill` |
| `layout.fit` | 默认 `contain`，另支持 `cover`；始终等比居中 |
| `audio` | 默认 `{mode:"silent"}`；可选连续音乐、原声、混音 |

`blurred`：前景适配宽度等大的方框，再按 104% 静态比例或图片曲线缩放；背景保留方形输入下的 236% 尺度并确保盖住画布。`blurred-fill`：前景适配整个画布，背景 cover 后模糊 35；适合泳装动态立绘的已有竖屏素材。`plain`：直接 contain 留边或 cover 裁切，不再加模糊背景。

C 只接受 `blurred` 布局，确保静图和视频使用同一 104% 前景尺度；静图段结束前应让缩放曲线达到端点。A 也只接受 `blurred`，B/D 可选三种布局。横竖比例改变后本工具保证不拉伸，不保证每个主体都恰好完整入镜；具体裁切需求应写进生成图和布局计划。

### 素材字段

每项均需 `id`（唯一）、`kind`（`image` / `video`）、`path`。额外字段如下：

| 类型 | 字段 |
| --- | --- |
| A/B 图片 | 不接受单段 `frames` 或 `scale_speed`；由模式及总长统一决定 |
| C 图片 | `pair_id`、`frames` 必填；`scale_speed` 默认 1，可填 `1.3333333333333333` |
| C/D 视频 | `source_duration_seconds` 必填，为完整源视频流时长；`source_start_seconds` 默认 0；`source_take_seconds` 默认剩余时长；`speed` 默认 1 |
| C 视频 | 另需与前一张图片相同的 `pair_id`；每个配对 ID 只出现一组 |

视频长度不能按“10 秒模型”标签猜测：让上游记录实际视频流时长，再写入 manifest。`--render` 会用 ffprobe 校验，差异超过约一输出帧就停止。缺音轨通过渲染前探测判断，不由扩展名判断。当前输入视频需方形像素，其他 SAR 需先正确归一化；不会把拉伸后的图像冒充等比输出。

A 使用整帧均分边界 `round(i×total_frames/N)`。B 将 `total_frames+(N−1)×transition_frames` 分给各输入，再叠加转场，最终仍是指定总长。C/D 按每段变速后帧数求和，减去每个边界的重叠。中间段过短会被拒绝，避免三段交叉窗口互相覆盖。

### 音频字段

```json
{
  "mode": "source+bgm",
  "path": "assets/music.m4a",
  "source_start_seconds": 0,
  "output_start_seconds": 0,
  "gain_db": -12,
  "source_gain_db": 0,
  "loop": false
}
```

- `silent` 只接受 `mode`，输出无音轨。
- `bgm` 只用连续音乐。`path` 必填，源/输出起点默认 0，`gain_db` 默认 −7，`loop` 默认 true。
- `source` 仅 C/D 可用，保留源声；只接受 `mode` 和 `source_gain_db`（默认 0）。
- `source+bgm` 仅 C/D 可用，保留源声并混音乐；`gain_db` 作用于音乐，`source_gain_db` 作用于原声。混音不自动归一化音量，限制器上限 0.95。

原声逐段按画面所用源区间裁切，拆分合法 atempo 段处理 0.1–10 倍变速，再统一为 48 kHz 双声道；无声视频和 C 中静图补等长静音。相邻段音频与视频使用同长度交叉淡化。BGM 连续挂在完整时间线上，不每段重新开始。`loop=false` 且音乐不足时停止，不静默截短视频。默认取源文件第一条音轨；不支持多音轨选择、独立台词轨或自动压低 BGM。

结尾淡出作用于全部画面和最终音轨；起点向前移一帧，使最后输出帧位于淡出终点。`intro_blur_frames` 是模糊/清晰分支的混合，与“高斯 sigma 每帧线性降低”并非同一实现。

## 输出与限制

成功后得到 `output.mp4` 与 `output.render.json`，包含输入哈希、实际帧数、参数和“待用户验收”状态。MP4 默认 H.264、CRF 18、veryfast、yuv420p；有声时 AAC 192 kbps。这里不继承历史项目的大体积 100 Mbps 投稿设置，也没有承诺 CBR。

输出、成功记录都拒绝覆盖；渲染使用独占 `.render.lock` 与输出目录下随机临时文件夹。正常失败清理本次临时文件；进程崩溃后若锁遗留，确认该渲染进程已停止再删对应锁，不要删除来源目录或其他任务缓存。成片与记录用同文件系统的无覆盖链接发布；不支持硬链接的目标文件系统会明确失败。

仅做文件检查时不运行任何媒体命令。新封装未做真实渲染，FFmpeg 需支持 libx264、xfade、acrossfade、gblur、blend、alimiter；多路高清 xfade 与逐帧 Pillow 动画可能较慢或占用较多内存。历史 Pillow 和 Premiere 的模糊、羽化、重采样不同；保留关键参数不等于逐像素复现。没有把任何原 PR/XML、个人目录、角色预设或商业音乐塞进 Skill。

纯数据测试：

```bash
python3 -m unittest discover -s skills/character-showcase-editing/tests -v
```
