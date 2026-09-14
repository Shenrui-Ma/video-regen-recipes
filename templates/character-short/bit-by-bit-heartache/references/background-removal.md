# 可选去背景：RMBG → alpha/mask → 明确RGB底色

仅在用户要求去背景、或同意纠正参考图背景带入视频时使用。已有透明立绘直接进入第三步；普通RGB参考不默认去背景。此步骤不生成新的角色图。

## 1. 节点与模型

- 节点来源与固定版本见[rmbg-model-manifest.json](rmbg-model-manifest.json)。使用公开`1038lab/ComfyUI-RMBG`仓库的`bd509b4750c81221b938684489c87187b0172208`；不要沿用已经失效的旧组织地址。
- 模型为`1038lab/RMBG-2.0`，revision为`1cd4787601caeb4c8e826dba7ea8e2163b5208df`，放在`ComfyUI/models/RMBG/RMBG-2.0/`。文件URL、SHA256、字节数另见可供下载器读取的[rmbg-models.json](rmbg-models.json)。本包不含权重或第三方模型代码。
- 节点GPL-3.0和模型使用权分开确认。先阅读[BRIA官方模型页](https://huggingface.co/briaai/RMBG-2.0)及适用许可，确认非商用/商用范围。镜像能下载不表示获得模型授权；官方页面需登录时由用户完成登录，不从镜像绕过授权。
- 模型含自定义Python代码，固定SHA不等于安全审计。安装前审阅固定版本代码、requirements与许可证，避免改动正在生成的共享环境。

仅在用户允许安装、目标实例没有活动任务且目录不存在时，在新实例的ComfyUI目录执行：

```bash
git clone https://github.com/1038lab/ComfyUI-RMBG.git custom_nodes/ComfyUI-RMBG
git -C custom_nodes/ComfyUI-RMBG checkout --detach bd509b4750c81221b938684489c87187b0172208
# python必须是该实例的虚拟环境解释器
python -m pip install -r custom_nodes/ComfyUI-RMBG/requirements.txt
```

已有节点先读取版本/本地修改/加载错误，不覆盖或重置。安装完在获准启动的独立实例中检查`/object_info/RMBG`；不要为当前生成任务重启共享服务。H3主安装流程不自动安装RMBG。

确认模型授权后，从模板目录显式获取这四个文件；`--root`替换为该实例真实的models目录：

```bash
python3 scripts/distribution/fetch_assets.py --manifest references/rmbg-models.json \
  --root ./h3-local/ComfyUI/models \
  --asset RMBG/RMBG-2.0/config.json \
  --asset RMBG/RMBG-2.0/birefnet.py \
  --asset RMBG/RMBG-2.0/BiRefNet_config.py \
  --asset RMBG/RMBG-2.0/model.safetensors
```

不带`--asset`不会下载可选权重。已有文件不同会拒绝覆盖；网络失败保留`.part`供核查。该模型约885MB，不是轻量Skill包的一部分。

## 2. 独立去背景图

使用[workflows/rmbg.api.json](../workflows/rmbg.api.json)，这是API图而非编辑器JSON。可用ComfyUI原生节点手动建立等价图：

- `LoadImage` → `RMBG.image`。
- RMBG参数：`model=RMBG-2.0`、`sensitivity=1.0`、`process_res=1024`、`mask_blur=0`、`mask_offset=0`、`invert_output=false`、`refine_foreground=false`、`background=Alpha`、`background_color=#FFFFFF`。
- 输出0 `IMAGE` → 第一个`SaveImage`，保存透明人物。
- 输出2 `MASK_IMAGE` → 第二个`SaveImage`，保存可查看的mask。输出1是`MASK`，不能直接接`SaveImage.images`。

Agent通过API执行时：将原参考图保存至任务独立的ComfyUI input子目录（或`/upload/image`且`overwrite=false`）；根据上传回执将`__CHARACTER_IMAGE__`绑定为真实input相对路径，将`__OUTPUT_PREFIX__`绑定为新的任务相对前缀。拒绝绝对路径和`..`。核对当前`/object_info`的参数及三个输出槽位，确认JSON不再含占位符。

提交前将完整图、源图SHA与新UUID写入任务独立attempt记录并落盘，再以`{prompt: 图, prompt_id: UUID}`向`/prompt`提交一次。保存实际返回ID，查询`/history/ID`直至该ID完成；响应不明先查原ID的queue/history，不重新提交。按history的两个SaveImage输出记录，从`/view?filename=...&subfolder=...&type=output`取回PNG并记录SHA。不得猜输出文件名、拿历史图冒充本次结果。

这是独立图片分割任务，不连接H3 Sampler或生成控制器。节点/权重缺失时先处理依赖，不能先提交H3并期待自动修好参考图。

## 3. 合成真正送入H3的RGB图

```bash
python3 scripts/character/prepare_character.py \
  --image ./rmbg-output/alpha.png --background '#FFFFFF' \
  --out-dir ./character-white
```

保留原图、alpha、mask以及`character-white/provenance.json`。用Pillow读回alpha/mask，检查尺寸一致、alpha既有前景又有透明像素、mask非全黑或全白；检查输出`character.png`为RGB，尺寸与经过EXIF方向处理的原图一致。把这些原件SHA和实际RGB SHA与本次prompt记录放在同一任务目录。机械检查不能证明头发、配饰和衣服边缘已经理想。

将**`character-white/character.png`**传给H3的`--character-image`。透明PNG的隐藏RGB可能仍有原背景，绝不能仅`convert('RGB')`或把保存alpha等同于H3已经使用白底。原图、mask、alpha留作证据，不作为H3主参考。

首段对照时沿用原seed、驱动、107帧和20步，仅变参考预处理，且先取得对照生成授权。已有两次首段试跑的技术证据见[first-segment-validation.json](first-segment-validation.json)；新机器安装和整片续接仍需实测。
