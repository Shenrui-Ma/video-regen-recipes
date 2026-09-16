# B 站取流的实际情况

整理日期：2026-09-16。以下为实测记录与工程注意事项，画质与可用性会随站点策略变化。

## 匿名能拿到什么

用本工具 `--probe` 实测两条视频（`yt-dlp 2026.08.19`）：

| 视频 | 匿名可用最高 | 站点提示 |
| --- | --- | --- |
| BV1BPgq6hEey（竖屏 1080×1920） | 1080p30（avc1 / hvc1） | `1080P 60帧 are missing; you have to become a premium member` |
| BV1LQ7j6WEyD（横屏 1882×1080） | 1080p30（avc1 / hvc1 / av01） | 同上 |

结论：**未登录可以解析到 1080p30 并完成下载**（已实测下载并合并成功）；`1080p60`、`1080p+`、4K、番剧与付费内容需要登录 cookie 或大会员。具体上限逐视频不同，不能写成通用保证。

## 为什么只接受页面链接

`upos-*.bilivideo.com` 这类直链带签名与过期时间（`deadline`、`upsig` 等参数），特点是：

- 几分钟到几小时后失效，写进模板等于写了会坏的地址；
- 绕过页面就丢失了标题、作者、BV 号，来源记录无从核对；
- 不同 CDN 节点行为不一致，排障成本高。

所以脚本只接受 `/video/BV…/`、`/video/av…/`、`b23.tv` 短链（会先解析成规范页面）以及 YouTube 的 watch / youtu.be 链接，其余一律拒绝，并提示“请改用视频页面链接”。

## 为什么不要指望“只下需要的几秒”

`yt-dlp --download-sections "*0-3"` 在这条链路上会把 CDN 直链交给 ffmpeg，而 ffmpeg 侧缺少必要请求头，实测直接失败：

```
[tls] IO error: End of file
Error opening input file https://upos-sz-estgcos.bilivideo.com/...
ERROR: ffmpeg exited with code 187
```

可行的替代：整条下载后用 ffmpeg 本地裁切（推荐），或选更低画质来减少体积。

## 格式选择的约定

- **按短边算画质**：`min(width, height)`。竖屏 1080×1920 记为 1080p，否则竖屏素材会被 `height<=1080` 误排除。
- **优先 h264（avc1）+ m4a**：后续 ffmpeg 裁切、抽帧、调色板生成的兼容性最好；没有 h264 时自动退到 hevc/av01。
- **显式绑定格式 id**：先探测再按 id 下载，避免 yt-dlp 版本变化导致选择器行为漂移。
- **合并输出 mp4**：`--merge-output-format mp4`，输出名固定为 `<视频ID>.mp4`，便于模板引用。

## 抓取记录的用途

记录（`<视频ID>.mp4.fetch.json`）不是为了“证明拿到了素材”，而是为了三件事：

1. **来源可核对**：`page_url` / `title` / `uploader` 对上用户说的那一支；
2. **状态可转述**：`quality_limited` 与 `notes` 让交付说明能如实写“这条只有 720p”；
3. **不被误当 pinned**：`redistribution: local-reference-only` 与哈希并列，明确“字节只代表本次抓取”，与媒体库固定 revision 的语义区分开。

## 与媒体库的分工

| 素材性质 | 正确做法 |
| --- | --- |
| 用户自己的成片、已获授权素材、需要严格复现的参考 | 放媒体库（如 `Shenrui-Ma/video-regen-assets`），固定 revision + 哈希，模板按 pinned 引用 |
| 第三方作品，仅用于本地动作/节奏参考 | 用本工具匿名抓取，只留本机，记录来源，不再分发 |
