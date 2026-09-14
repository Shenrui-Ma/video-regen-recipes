# 原生续接工作流恢复范围

> 历史来源记录：本页描述旧实现/回收阶段。新安装使用 [当前生成路径](generation.md)与[环境说明](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/667eafddb9f42bb6c72ad27b665def9ada36df45/environments/h3/README.md)，不需要旧私有Save/Load/Trim节点。


当时的串行控制器、四份重建 API 图及部分 History 回读仍有保存。当前运行图不再放在本仓库：Toolkit 的 [H3 Core AV latent 续接包](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit/tree/af3dea3d05450eb2910f43f795a2eb6f346d06dc/workflows/h3/ref2va-core-continuation) 提供首段／续段两份参数化图，具体 commit 与逐文件 SHA 见 [workflow.lock.json](workflow.lock.json)。

## 恢复到哪一层

- 四份重建图节点数为18／21／21／21，保留原链的节点与连线。
- 第3、4段各有10个节点的历史 `/history/<prompt_id>` 回读摘录，节点与 inputs 逐对象等于重建图。其他节点未由原 History 逐项确认。
- 第1、2段有控制器和 sidecar 参数证据，未恢复完整原始提交体。
- 尚未找到完整编辑器布局或四份完整原始 History。不能把重建图称为原 UI 工作流。
- 本次另核对远端正式运行目录，四份 sidecar 与本地留存逐字节相同；该目录的已检查 MP4 标签没有保存 workflow/prompt。

公开版替换了机器路径、输入文件名和输出前缀；seed 用十进制字符串保存，提交 API 前转成整数以免浮点失真。源图 SHA 与公开版 SHA 分别记录。原提示词错误也仍属于历史对照，不作为新角色提示词。

## 新任务怎么用

Agent 使用 `first.api.template.json` 生成首段，再按硬件分段计划重复使用 `continue.api.template.json`，无需四份固定段图。绑定角色图、该段参考视频、提示词、采样长度、发布长度、seed、输出前缀及前驱 latent；参数类型和元数据规则见 Toolkit 的对应 README。

图已恢复不等于依赖已安装。当前链路只用 Core 官方节点加一个 `MiniMaxH3MotionContext`，不再依赖作者的私有 `HermesH3Continuation`；但干净环境安装与首段／续接的真机验收仍未完成，模板保持未完成从零生成验收的状态。
