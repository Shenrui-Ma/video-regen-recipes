# 角色参考图输入

Heartache接受现成的角色图片。原示例爻光图的制作经历仅作素材来源记录，不成为模板使用者的操作步骤。

## 用户提供图片

不透明RGB原图可以直接传给H3运行入口的`--character-image`。透明PNG应先用下面的helper明确合成RGB，再传`character.png`；不能直接丢弃alpha。运行入口遇到未合成的透明参考图会在创建工作目录前拒绝，并指向helper。只做可解码、尺寸和来源检查；不重新生成、不改服装或身份。

若需要规范化PNG和保留来源记录，可通过`terminal`执行：

```bash
python3 scripts/character/prepare_character.py --image ./my-character.jpg --out-dir ./character-input
```

helper与运行入口的图片检查均需Pillow（环境锁为11.3.0），保存逐字节原件`source.png`/`source.jpg`和H3可用的RGB `character.png`；处理EXIF方向及格式，不裁剪、缩放或重绘。透明度默认合成到白色`#FFFFFF`，包括RGBA、LA、调色板和PNG透明色键；不透明RGB像素不受背景参数影响。EXIF旋转可能交换宽高，但不改变主体比例。`provenance.json`记录输入输出SHA、来源、背景颜色、是否执行alpha合成、输出模式与尺寸。`style_change: false`表示未重绘/改风格，不表示未进行背景合成。

## 透明输入与可选去背景

H3参考图接受RGB。RGBA的隐藏RGB像素可能仍是原背景；`convert('RGB')`仅去掉alpha，会让原背景重新出现。helper使用Pillow `Image.alpha_composite`先合成，再转RGB；保留原始透明文件用于回溯。需要其他底色时明确指定六位十六进制颜色（引号不可省略）：

```bash
python3 scripts/character/prepare_character.py --image ./cutout.png --background '#FFFFFF' --out-dir ./character-white
```

将`./character-white/character.png`交给H3的`--character-image`。不要误传同目录透明的`source.png`。已是透明立绘时无需运行RMBG；普通JPEG的白底合成也不会自动识别/去除已有背景。

**RMBG是可选前处理，不是默认生成依赖。** 仅在用户需要去背景时，按[background-removal.md](background-removal.md)使用 Toolkit 的[去背景工作流](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafd/workflows/images/rmbg-2-alpha/)，保留原参考、alpha和mask后再运行本helper。本helper不会安装RMBG、下载权重、提交ComfyUI任务或调用生图模型。

## 用户未提供图片

1. 从用户请求确定角色全名和所属作品；例如“一句话用某角色做Heartache”中的角色就是检索目标。
2. Agent用`web_search`查该角色官方立绘，优先作品官网、官方角色介绍页或权利方官方发布。资料站转载需追溯官方原图；不把同人图、AI生成图或相似角色当作官方图。
3. 用`web_extract`/浏览器核对页面身份与图源，必要时用`vision_analyze`确认图片。记录来源页面URL和实际图片URL；页面文字不能证明图源时保留不确定性。
4. 下载原图并核验可解码、人物未被错误截断、不是缩略图/HTML。公开可访问不代表获得商用或二次传播授权，保留来源与适用限制。
5. 角色存在歧义、可靠官方原图不可取得或需登录时，向用户询问必要信息/请其提供图片，不擅自改角色或开启生图。

已核对的公开PNG/JPEG直链可以通过`terminal`下载：

```bash
python3 scripts/character/prepare_character.py \
  --url 'https://OFFICIAL_IMAGE_HOST/character.png' \
  --rights-note '官方来源页面URL与使用范围说明' --out-dir ./character-input
```

直链必须换成实际检索确认的地址。此CLI不内置搜索引擎；查找官方角色立绘由Agent按上述步骤完成。若原件是其他格式，先保存原件，再做必要的格式转换并记录来源。

## 安全与验收

URL下载使用临时文件、32MiB上限、真实图片解码与可选`--sha256`核验。拒绝私网、带凭据URL、输出路径穿越和用户目录软链接；不使用来源文件名构造输出路径。URL的DNS检查不是多租户SSRF隔离层，只用于已审阅的公开图片地址。

输出目录必须全新；已有目录、同名输出和软链接目标不会被覆盖。失败时不把缺少`status: complete`来源记录的目录当成有效输入，重试使用新目录。

角色输入helper没有ComfyUI客户端、模型下载或采样提交入口。运行`python3 -B -m unittest discover -s tests -p test_character_input.py -v`验证本地图保留、URL获取、坏图清理、路径安全、真实alpha合成、尺寸与无生图能力。随后将RGB `character.png`交给`scripts/runtime/heartache.py`的视频流程。
