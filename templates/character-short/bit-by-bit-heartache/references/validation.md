# 验收范围与复测

## 模板交付范围

本包供Agent从用户的一句话和角色参考图开始：读取SKILL.md与README，核对运行环境，获取固定驱动与配乐，准备角色图片和分段图，使用H3串行生成与真续接，按发布区间拼接并连续配乐。仅指定角色时先查官方立绘，资料不足时询问必要信息。

## 已有证据与本次验证

- 已有历史H3运行的来源、参数与复现记录见reproduction.md和native-continuation.md。它们不是新机器使用本包完成推理的证据。
- 0.2.0模板已在既有Linux/A100环境用真实角色参考完成两次第一段H3生成，包括可选RMBG＋白底RGB参考。每段107帧，技术校验和交付读回SHA见[first-segment-validation.json](first-segment-validation.json)。这不证明干净安装或完整新角色真续接已验收。
- 0.3.0对去背景输入、媒体预检、后处理失败恢复和轻量分发补充CPU测试。测试中的合成视频和latent只是离线夹具；本轮修改不额外提交GPU生成。
- 分发验收要求：ZIP逐文件SHA及大小匹配，排除handoff.json、虚拟环境和运行目录；解压到干净目录后测试与smoke通过；使用公开URL获取真实驱动，通过SHA、视频解码与准备命令核验。验收摘要由发布包旁的报告保存。
- `preflight`只检查明确传入的环境证据。平台override是目标计划，不能证明当前硬件兼容；离线contract不含用户文件枚举。

## 使用者机器仍需完成

固定推理环境为Linux x86_64、CPython3.10和NVIDIA/CUDA。干净Linux安装、目标pip check、模型加载及新角色完整H3推理尚未由本次封装执行，`clean_install_inference_verified=false`。macOS验证仅涉及CPU准备、脚本和后处理。

首次运行需核查本机容量并完成首段及一次真续接校准；成功后保留已生成结果继续同一计划。完成时核验真实history success、前驱latent、素材及工作流SHA、连续发布区间、总帧数、24fps、1344×768、持续配乐与完整解码。人物身份、动作跟随和接缝效果由使用者视觉确认。

## 离线复测命令

从解压后的Skill根目录执行；轻量环境只需Python3.10+、Pillow11.3.0与FFmpeg/ffprobe：

```bash
python3 -B -m unittest discover -s tests -v
python3 scripts/runtime/heartache.py smoke
python3 scripts/distribution/fetch_assets.py
python3 scripts/distribution/fetch_assets.py --check
```

下载素材不是提交推理；只有明确的`run --execute`才运行H3。目录中的历史剪辑入口仅用于明确要求的重剪，不可拿历史角色成片充当新角色生成结果。
