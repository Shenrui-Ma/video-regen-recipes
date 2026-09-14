# 按需获取素材：默认分发包不含媒体

默认 ZIP 只保留母技能文档、脚本、工作流、补丁、许可证与 JSON 清单。**PNG／其他图片、音乐、视频、latent、模型权重及未知二进制格式均不随默认包分发**，不限于 `assets/` 目录。打包使用文本文件类型白名单；不会删除、改写现有本地素材。

从技能根目录执行：

```bash
# 默认只获取 runtime 的 577 帧动作参考与音乐；不下载历史爻光图片或剪辑
python scripts/distribution/fetch_assets.py

# 只校验默认两项：无网络、无写入；缺失或哈希不符时退出码为 2
python scripts/distribution/fetch_assets.py --check

# --assets 替代默认选择；填写相对 assets/ 的清单路径，可一次指定多个
python scripts/distribution/fetch_assets.py --assets default/music.m4a
python scripts/distribution/fetch_assets.py --assets default/yaoguang.png
python scripts/distribution/fetch_assets.py --check --assets default/yaoguang.png

# 可选：明确复用历史剪辑时，单独获取所需片段
python scripts/distribution/fetch_assets.py --assets default/clips/part-01.mp4 default/clips/part-02.mp4
```

`--without-default-character` 继续兼容旧命令，但默认已不选历史角色图；此参数会进一步排除显式选择中的历史角色图。新角色应通过角色输入流程提供，不能用历史爻光图冒充用户指定角色。

## 可验证的公开来源

[`runtime-assets.json`](runtime-assets.json) 为每项素材记录公开 HTTPS URL、精确字节数、SHA-256、用途及 `download_by_default`。下载源是 [Video ReGen 媒体库](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets) 的固定 revision，URL 采用 `resolve/<revision>/<path>`，因此以后改动媒体库不会改变已发布内容的字节。下载器验证字节数和 SHA-256；同名文件已匹配则跳过，不匹配则拒绝覆盖。

| 清单路径 | 默认获取 | 用途 |
| --- | --- | --- |
| `reference/heartache-driver-577f.mp4` | 是 | runtime 冻结动作参考：1344×768、24 fps、577 帧；160208343 字节 |
| `default/music.m4a` | 是 | 音乐输入；按成片时长截取并淡出 |
| `default/yaoguang.png` | 否 | 可选历史爻光身份参考；2352×2352，仅用于明确要求的示例 |
| `default/driver.mp4` | 否 | 历史原始动作视频，约 45 fps；**不能替代 runtime 的 577 帧参考** |
| `default/clips/part-01.mp4`、`default/clips/part-02.mp4` | 否 | 历史已发布剪辑，各 158 帧 |
| `default/clips/part-03.mp4`、`default/clips/part-04.mp4` | 否 | 历史 canonical 完整解码，各 175 帧 |

runtime 动作参考 SHA-256：`e63386ab88bf4a11dc2fd859b0075099229cad44d77366a220c6e0bb0ba0ca0d`。

[`default/manifest.json`](default/manifest.json) 保留历史素材的媒体规格与处理记录。PNG 已去除内嵌工作流、文字和 EXIF；压缩图像数据保持不变。历史视频采用流拷贝移除容器元数据，剪辑去除音频并使用独立音乐轨。这些历史片段不是新角色生成结果，也不能代替 `latent.safetensors` 做原生续接。

离线缓存可通过 `--cache-dir` 指定：将原始文件按清单文件名放入缓存目录，下载器复制前后均校验；未命中缓存仍会尝试公开 URL。`--asset-root` 可指定目标素材目录。下载中断只留下 `.part`；若校验失败，检查并仅移除对应 `.part` 后重试，不会覆盖已有目标文件。`--check` 是严格只读模式。

## 打包与权重边界

```bash
# 输出必须在技能源目录之外，且不能覆盖现有 ZIP
python scripts/distribution/package_skill.py --output ../heartache-lightweight.zip
python scripts/distribution/package_skill.py --verify ../heartache-lightweight.zip

# 兼容旧行为的显式全量包：包括已有本地二进制文件，不下载素材；不是轻量包
python scripts/distribution/package_skill.py --full --output ../heartache-with-local-assets.zip
```

`BUNDLE-MANIFEST.json` 记录包含文件及被省略文件的字节数与 SHA-256；省略清单的兼容字段名为 `omitted_downloadable_assets`，**不代表其中每个任意本地二进制都有公开下载源**。素材获取以 `runtime-assets.json` 为准；模型来源、固定版本及位置另见 [环境依赖锁](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/dependencies.lock.json)，模型下载／安装是单独步骤，不由 `fetch_assets.py` 执行。默认包不含任何模型权重；`--full` 会带入已存在的本地二进制（包括权重），分享前须自行检查体积及授权。

## 授权

素材由贡献者提供作为本案例输入和演示；仓库 MIT 许可不自动覆盖角色 IP、原视频和歌曲，不附加第三方素材的商业使用或自由再分发授权。来源见[说明](../sources.md)。公开 URL 不等于授权，获取或再分发前须检查对应权利。
