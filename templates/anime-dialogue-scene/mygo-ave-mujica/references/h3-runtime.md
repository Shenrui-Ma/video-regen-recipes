# H3：从剧情 JSON 到可核验的分段视频

本页使用**独立 Ref2VA 联合音视频采样**。每段重新绑定人物、场景和声音，生成后剪辑拼接。串行提交便于控制资源和恢复任务，不代表上一段 latent 续接。

具体图由 [ComfyUI Toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/main/workflows/h3/ref2va-dialogue)维护；本包保留[固定来源](../workflows/toolkit-source.json)对应的离线副本，便于构建器稳定使用。更新时先核对commit与哈希，不自动漂移。

## 1. 固定第一轮配置

| 项目 | 本模板默认 |
|---|---|
| 分段 | 六段：前五段各 243 帧，末段 226 帧 |
| 画布 / 帧率 | 768×448 / 24 fps |
| 总长度 | 1441 帧，约 60.041667 秒 |
| 采样 | `res_multistep` / `simple` / 20 步 / `denoise=1.0` |
| 条件 | `BasicGuider`；不补写 CFG、negative conditioning 或 SigmaShift |
| 参考 | 人物身份图、说话人三视图、场景图、说话人音色 WAV |
| 第一轮后处理 | 拼接、字幕；先验收原片再考虑超分 |

先跑完整第一段，再跑余下五段。若只想做更便宜的独立试片，可另建一个 **175 帧（7.291667 秒）**项目并缩短台词；它不等同于六段方案的第一段。

历史有四组素材，参数不要混用：

| 路线 | 尺寸 | 段数 / 目标帧数 | 本包用途 |
|---|---|---|---|
| 六段基础版 | 768×448 | 6 / 1441 | 默认参数来源 |
| 八段对白版 | 768×448 | 8 / 1451 | 单段更短，剧情分得更细 |
| 八段动作版 | 1088×608 | 8 / 1451 | 动作与机位更复杂时另做版本 |
| 软空间参考版 | 1088×608 | 3 / 576 | 额外角色化构图参考；历史为局部重做，未合入旧全片 |

这些历史段落有工作流、History 与媒体元数据核对记录。本仓库重新参数化的脚本、示例和跨机器环境仍需首段实跑；Ave Mujica 示例也需要重新验证声音、身份与表演。

## 2. 模型与实际节点

历史基线的四个模型文件如下。它们是兼容组合的参考，**文件名不代表已下载、完整或适合当前机器**。以所选发布方的模型说明、下载文件哈希和本机节点枚举核对后，填写 `episode.json.model_files`。

| 字段 | 历史文件名 | ComfyUI 模型目录 |
|---|---|---|
| `diffusion_model` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `diffusion_models/` |
| `text_encoder` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders/` |
| `video_vae` | `minimax_h3_video_vae_fp16.safetensors` | `vae/` |
| `audio_vae` | `minimax_h3_audio_vae_fp32.safetensors` | `vae/` |

填的是**各节点下拉框返回的精确相对名称**，通常不含上表模型目录前缀。`weight_dtype=default` 不改变权重文件本身的量化格式。首次不要加 Turbo LoRA、缓存、替代 attention、修脸或插帧节点；这些要分别验证。

使用已支持 H3 的 ComfyUI 安装，记录实际 core/node 版本。普通 ComfyUI 安装不保证自带这些节点。通过当前实例 `/object_info` 逐项核对 `MiniMaxH3ReferenceToVideo`、`CLIPLoader(type=minimax)`、两路 VAE、采样器及 `SaveVideo` 的输入/枚举/输出槽；历史生成环境的精确 core commit 未确认，不能把其他实验环境的版本当成已验证版本。

实际主链：

```text
人物/场景 LoadImage + 声音 LoadAudio
  → MiniMaxH3ReferenceToVideo（conditioning 输出 0，联合 latent 输出 1）
  → BasicGuider + RandomNoise + res_multistep + simple/20
  → SamplerCustomAdvanced
  → 同一联合 latent 分别经视频 VAE 与音频 VAE 解码
  → CreateVideo（24fps）→ SaveVideo（MP4/H.264）
```

该最小图的基础节点都位于输出链上。可按需省略没有使用的三视图及对应 `LoadImage`，同时重排提示中的图号；不要删除音频 VAE 或自行添加前段 latent 边。

## 3. 准备项目与输入绑定

把示例剧情 JSON 复制到**新建的用户项目**，命名为 `episode.json`。所有素材路径都相对此文件所在目录；不要在已安装的模板目录里生成素材和输出。

```text
episode.json
assets/characters/<id>/identity.png
assets/characters/<id>/turnaround.png
assets/voices/<id>/reference.wav
assets/scenes/<id>/reference.png
bindings.json
```

脚本需要 Python 3.9+ 和 PATH 中的 `ffprobe`（FFmpeg 提供）。只做读取、检查和导出，不启动服务、不上传、不提交 GPU 任务。

以下命令中的 `TEMPLATE_DIR` 是仓库内本模板目录，`PROJECT_DIR` 是用户的新项目目录；执行前设置实际值。

```bash
python3 "$TEMPLATE_DIR/scripts/build_episode.py" "$PROJECT_DIR/episode.json" --shot 01 --check-local
```

先用 `--shot 01` 只准备和检查首段实际使用的素材，其他段未使用的角色/场景可以暂留占位。需要多段时重复 `--shot 01 --shot 02`；省略 `--shot` 才检查全部。模型配置始终必须填好。

检查内容：文件实际存在且可读取、图片尺寸、WAV 的实际 PCM 编码/时长/声道、SHA-256、角色引用、种子、帧网格和画布尺寸。每段最多三位说话人，每条参考音频 2–15 秒，总时长不超过 15 秒。静音、混入音乐、多人串声仍须试听，媒体元数据不能证明音色素材可用。

本包按历史输入范围保守限制每段最多八张参考图；这是模板边界，不声称模型的绝对上限。宽高必须为 32 的倍数，帧数采用 `17*k+5`：175 / 226 / 243 都有效，240 不属于该网格。

接入环境二选一：[本地 ComfyUI（默认）](../../../../docs/comfyui-local.md) / [远程服务器](../../../../docs/comfyui-remote.md)。生成、提交、恢复共用 [ComfyUI 执行协议](../../../../skills/comfyui-reference-images/references/execution.md)，本页把验收目标扩展为音视频。

### `bindings.json` 怎样产生

1. 将已经检查过的图片和 WAV 放入**目标实例**可访问的 input 目录。图片可按公共 Skill 上传；声音使用当前实例确认支持的上传方式，或复制到该实例 input 后核验，不能凭空假设存在 `/upload/audio`。
2. 若上传响应为 `{"name":"identity.png","subfolder":"episode-a","type":"input"}`，绑定名称为 `episode-a/identity.png`。已有素材也要核对它在目标实例中的实际位置。
3. 核验目标文件与本地文件的 SHA-256 一致，再写绑定账本。可通过服务支持的输入读回或受控文件读取计算哈希；上传返回文件名本身不是哈希校验。
4. 账本按本地 SHA-256 索引。同一文件多处引用可共用一项；不同内容不能绑定同一个目标名称。

结构示意，尖括号必须换成实际检查结果：

```json
{
  "schema_version": 1,
  "files": {
    "<64位小写SHA256>": {
      "name": "episode-a/identity.png",
      "sha256": "<同一64位小写SHA256>"
    }
  }
}
```

**构建器只核对该记录与本地文件一致，不替代服务器读回校验。** 不允许通过编一个 input 名称来跳过上传，也不接受客户端绝对路径、`..` 或 `[output]`/`[temp]` 标记。

## 4. 离线构建并检查第一段

```bash
python3 "$TEMPLATE_DIR/scripts/build_episode.py" "$PROJECT_DIR/episode.json" \
  --shot 01 --bindings "$PROJECT_DIR/bindings.json" --output "$PROJECT_DIR/build-v1"
```

输出目录必须不存在。所选段缺素材、占位符、绑定或非法参数都会停止；检查全部通过后才创建输出。首段成功后，补齐余下素材与绑定，用新的输出目录构建余下段，或省略 `--shot` 构建全部。构建全部也不会自动提交任何一段。

生成：

- `prompts/<shot-id>.txt`：完整实际提示词。
- `api/<shot-id>.json`：可交给 ComfyUI 接入层检查并提交的 **API 节点图**。
- `manifest.json`：帧数、图哈希、种子、素材哈希和绑定顺序；状态为 `built-not-submitted`。

`episode.json` 和 `manifest.json` 是参数/台账，不能发给 `/prompt`。仓库里的 `ref2va.api.template.json` 还有占位符和待生成的素材节点，也不能直接提交。只有导出的 `api/*.json` 才是完整图。

构建器按以下规则自动编号，每段重新开始：

| 类别 | 顺序 |
|---|---|
| `<Subject N>` 人物 | 本段 `cast` 顺序 |
| `<Subject N>` 场景 | 全部人物之后单独一个编号 |
| 参考图片 | 全部 cast 身份图 → 说话人三视图 → 场景图 |
| 参考声音 | `dialogue` 中说话人**第一次出现**的顺序，重复台词不重复加载 |
| `(S1)` 等发声编号 | 与参考声音同序，独立于 cast 顺序 |
| API 素材输入 | 从 0 起算：`ref_images.ref_image_0` / `ref_audios.ref_audio_0` |
| 提示词素材编号 | 从 1 起算：`<Picture 1>` / `<Audio 1>` |

在 `visual_description` 中写 `@tomori` 等角色 ID，构建器会替换为该段正确的 `<Subject N>`；未知角色、不在 `cast` 中的角色或手写参考编号都会报错。`appearance`、场景描述、动作与 `delivery` 用英文，`dialogue.text` 只写希望生成的原语言台词，不手动添加 `<d>`、语言或发声标签。

顶层 `dialogue_language` 默认 `Japanese`，本包接受 `Japanese` / `English` / `Chinese`。构建器将每句写成 `<Subject i> (Sj) ... <d>[Japanese] 台词</d>`，把 `(Sj)` 绑定到同号 `<Audio j>`；切换语言也要更换对应台词并重新试听，不代表任意声线跨语言都已验证。六段式中的 `retention_analysis` 不承担发声编号绑定。

提示词的 `summary` 使用 `[reference generation + audio reference]` 前缀；`retention_analysis` 为每个人物写 `fully_preserved`、场景写 `weak_reference`、每条声音写 `reference`。身份图和可用三视图一起归入同一人物的 Subject 定义，不另建 Picture 定义。`non_diegetic_music` 只填 `N/A`；这些是生成条件，仍需检查成片是否出现了不需要的配乐。

例如 cast 顺序为 `[tomori, anon]`、第一位说话人却是 anon：她是 `<Subject 2>`、`(S1)`、`<Audio 1>`；后说话的 tomori 对应 `<Subject 1>`、`(S2)`、`<Audio 2>`。这几组编号不可机械地全部写成同一个数字。

默认说话人必须有三视图。要节省前置出图，可把对应 `turnaround_image` 设为 `null` 或省略，并显式加 `--allow-missing-turnarounds`；实际省略项会写入 manifest。已经写了文件路径但文件不存在时仍报错，不静默跳过。省略三视图后的效果需重新检查。

## 5. 提交、验收与恢复

实际运行命令见 [单段执行器](running-shots.md)；它消费本页生成的 `api/01.json`。本页构建器始终只离线导出。

接入层先读 `/system_stats`、`/object_info`、`/queue`，核对目标服务、资源和模型实际枚举。脚本离线通过并不证明显存足够或节点实现兼容。单实例先只安排一个视频推理任务；首次只提交第一段，生成、解码、保存、下载和语义检查全部通过再继续。

1. 提交前保存 API 图、图 SHA、种子、唯一运行前缀和提交意图；提交后立刻保存返回的新 `prompt_id`。
2. 围绕该 ID 查询 queue/history。采样到 20/20 后还可能在进行两路 VAE 解码和保存，不能当作完成。
3. History 成功后，从输出记录读取真实文件名。下载到 `.part`，验证 SHA、实际解码帧数、画幅、24fps、SAR、音轨和完整音视频解码后，再重命名。
4. 将**请求帧数**与**实际解码帧数**分别记录并对比。六段目标为 243×5+226；不要为凑整数一分钟擅自丢帧。容器时长也不能代替整数帧数。
5. 看画面并听声音：角色/服装、声线归属、口型、台词完整度、动作方向和镜头前后位置关系。技术通过与语义通过分开记；没有听看能力时明确待审。

提交超时或断线：先读原 state 和 ID，查原 queue/history；运行中就接着等，成功就取原输出。提交状态不明时标 `unknown`，不要重投。服务重启后 History 缺失也不证明任务从未执行。

语义返修只新建受影响段的版本，保留旧图、种子、文件和拒绝原因。若声音听起来互换，先核对当前图、speaker 顺序、素材哈希和 WAV 本身；绑定正确时应修正条件或重采样，不盲目对调 WAV。独立分段允许只重做一段，但相邻剪辑连续性要重新检查。

## 6. 什么时候升级

- **更细的剧情节奏：**改为八段，前七段 175 帧、尾段 226 帧，并重写每段动作和台词密度。不是把六段视频机械切成八段。
- **人物站位反复出错：**先简化到一个主要机位，把前后/左右/朝向写成镜头间持续关系；再制作人物已放在正确位置的软空间参考图。当前图只把它作为场景参考输入，不锁定生成的第一帧或最后一帧。
- **需要硬首尾帧或 latent 续接：**选择与对应模式匹配的权重和节点，另建并验证工作流。不能在提示中写“first frame”就宣称当前 Ref2VA 图实现了硬控制。
- **更高原生分辨率：**1088×608 是历史动作版参数，计算开销更高。先确认资源并做单段；不能把 1080×600 直接当作该画布的合法替代。
- **人脸二次采样：**历史仅完成候选环境/图的准备，未验证正式全片修脸。它不是基础链必要步骤；超分也不能修正错误的脸型、站位或说话人。

基础片验收后再做后期。改变模型、步数、节点或生成模式时记录为新配置，不沿用“默认基线已通过”的结论。
