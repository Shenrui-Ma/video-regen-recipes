# FFmpeg 预检与后处理恢复

## 先验证实际runner环境

从模板目录使用将来运行`heartache.py`的同一终端、Python和PATH执行。`ffprobe`成功只说明能读媒体，不证明AAC编码可用。

```bash
command -v ffmpeg
command -v ffprobe
ffmpeg -version
ffmpeg -v error -f lavfi -i anullsrc=r=44100:cl=stereo \
  -t 0.1 -c:a aac -f null -
python3 -B -m unittest discover -s tests -p 'test_runtime_media.py' -v
```

最后的测试会生成独立临时夹具，实际执行驱动切片、发布画面拼接、AAC配乐、完整解码和画面哈希校验，不访问ComfyUI或启动GPU推理。合成夹具不是H3成片。

旧Linux系统FFmpeg曾把AAC标为experimental，造成H3与视频/latent保存成功后才在配乐时报错。选择支持AAC的新版FFmpeg，不默认添加`-strict -2`。若环境已有`imageio-ffmpeg`，可用该环境的Python执行以下命令定位其附带二进制：

```bash
python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())'
```

核对输出后，在任务私有`bin`目录为这个已验证二进制创建名为`ffmpeg`的软链接，只为本次runner设置`PATH="$PWD/task-bin:$PATH"`。`ffprobe`仍须真实可用，并重新执行上述完整测试。不要修改系统链接、全局shell配置或重启共享ComfyUI。没有这个包时，按系统官方安装方式准备新版FFmpeg，不因本例强制安装另一套Python/CUDA环境。

## 失败后识别已经完成的部分

- 原prompt没有成功：先查准确prompt的queue/history和错误，不能把后处理恢复当作新提交许可。
- 采样成功、解码失败：保留两路latent，按[生成恢复规则](generation.md)核验后做无Sampler解码。
- `segments/segNN/verification.json`、两路latent和`published.mp4`均存在且SHA匹配，只有拼接/配乐失败：修复媒体工具后恢复同一工作目录，只补后处理。不要删除`job/state.json`、提交意图、原history或段验收记录。
- `final.mp4`存在但没有通过验收，不表示成片完成。未知来源、身份不匹配或外部修改的文件应拒绝覆盖；先保留错误与原文件，再依据实际报告处理。

## 旧版本留下损坏final.mp4时

0.2.0可能直接写出一个不完整的`final.mp4`。先确认该累计目录的`assembly-intent.json`与原发布视频/音乐SHA及连续区间一致，原段`verification.json`全部可验证，而且累计目录没有成功验收记录。保存FFmpeg错误，**将该整个失败累计目录改名到同级、尚不存在的备份名**（例如`through-seg01.failed-aac`），不要删除文件，也不要移动`segments/`或`job/`。随后用原工作目录与原段号运行下一节命令，重新创建累计目录完成后处理。

已验收成片被改动、intent不匹配、目录来源不明或无法确认谁仍在写时停止；不能按这个流程绕过未知文件保护。新版本的原子发布会在输出验证通过后才公布`final.mp4`，普通编码失败不会将半成品公布为成片。

## 恢复命令

修复FFmpeg并测试后，使用原工作目录、原ComfyUI文件根目录和原host；`N`设为需要恢复的已生成前缀段号：

```bash
N=1
python3 scripts/runtime/heartache.py run \
  --work-dir ./work/heartache-01 --comfy-root ./h3-local/ComfyUI \
  --host http://127.0.0.1:8188 --until-segment "$N" --execute
```

该命令会继续查询原任务并复核已生成产物，不能在提交意图、状态或产物互相矛盾时强制新采样。恢复范围不应超过原用户授权；使用原段号可避免顺带提交尚未生成的后续段。

若要换机器完成后处理，复制的每个发布视频和音乐须与原段验收及输入清单SHA一致。调用随包`media.assemble`时使用原`run.json`中的连续发布行，输出到全新目录；不导入或调用生成控制器。音乐从累计时间线零点铺设，不重复裁context，不使用`-shortest`隐藏短音轨问题。

## 完成条件

每个累计版本必须核验帧数、24fps、1344×768、单条连续音乐、音轨覆盖时长、完整解码和文件SHA。解码画面哈希须与按顺序连接的已发布片段一致。平台投递还要核对当前目标、消息回执和可读取的文件；不能把本地文件存在当成已送达。
