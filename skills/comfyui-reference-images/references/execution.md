# 准备、执行、恢复与交付

## 1. 确定可执行图

优先使用用户授权的图或发布方模板，在 ComfyUI 中导出 **API 格式**。API 图是 node ID 到 `class_type`/`inputs` 的映射；含顶层 `nodes`/`links` 的编辑器 JSON 不能直接提交。

- 展开子图和动态输入；不要按 `widgets_values` 数组位置猜参数。无法可靠转换就通过当前前端导出，缺边也不能凭邻近节点猜接法。
- 选择交付所需的 `SaveImage` 节点并向上追踪。标记首轮、二次采样、修脸、放大等分支；文件名和最终分辨率不能证明处理链。
- 对照实时 `/object_info`：节点存在、required 输入齐全、枚举值和数值范围合法、引用节点及输出槽匹配。版本差异以该实例和节点文档为准。
- 对照实际模型枚举填精确相对名称。固定 LoRA 链、文本编码器、VAE；解析正负提示中的 embedding 等隐藏依赖。
- 绑定角色、场景、镜头用途和输入哈希；修改工作流副本。提示词不能遗留 `{{...}}`、旧角色、旧服装或错误画幅。
- 首次先单张、batch size 1，使用所选模型推荐的有效尺寸和采样配置；不把低步数测试图当最终画质证明。

## 2. 输入、提交、监控

以下是自托管 ComfyUI API，路径附加在运行时 `COMFY_BASE_URL` 后。[官方端点](https://docs.comfy.org/development/comfyui-server/comms_routes)

| 顺序 | 请求 | 成功条件 |
|---|---|---|
| 上传（需要输入图时） | `POST /upload/image`，multipart 文件字段 `image`；使用唯一名称、`type=input`、不覆盖已有文件 | 记录返回的 `name/subfolder/type`，将服务识别的名称绑定到加载节点 |
| 提交 | `POST /prompt`，JSON：`{"prompt": API_GRAPH, "client_id": RUN_UUID}` | 无 `error/node_errors`；立刻保存 `prompt_id` |
| 核对 | `GET /queue`，任务太快完成则查 history | 本任务对应的图、模型、图片、seed、输出前缀正确 |
| 等待 | `GET /history/{prompt_id}`；可选 WebSocket `/ws?clientId=RUN_UUID` | history 显示成功且目标输出存在；出现错误即记录失败 |
| 下载 | `GET /view?filename=...&subfolder=...&type=...`，参数 URL 编码 | 只取本任务目标输出节点记录的文件 |

上传名包含子目录时用服务返回的信息组装，不能使用 Agent 机器的绝对路径。输出先写项目 `.part`，检查内容类型、大小及完整解码后原子重命名；拒收伪装成图片的错误页。下载参数不要转成任意本地路径，禁止 `..` 越出项目目录。

以 `prompt_id` 隔离任务。WebSocket 的某个节点完成、进度 100%、HTTP 200 都不等于整图成功。轮询采用有限超时与退避，不高频请求。缓存命中是有效结果；需要新候选才改 seed，不为逃避缓存乱改图。[官方 API 示例](https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example.py)

## 3. 不重复执行的恢复规则

| 现象 | 下一步 |
|---|---|
| 提交超时，没收到 ID | 用已记录的唯一运行前缀、client ID、API 图哈希在 queue/history 核对。服务不保证幂等；状态仍不明就标 `unknown`，不要自动重复提交 |
| 已有 ID，网络中断 | 重连后查同一 ID；在队列中继续等，成功则取文件，失败则读取原因 |
| history 没有该 ID | 再查 queue；服务重启可能丢失内存记录，结合本地台账和服务器输出核对。缺证据不当成“从未执行” |
| 缺模型或尺寸不匹配 | 核对目录、枚举、底模/编码器/VAE/LoRA 家族；不能随机换一个同名近似文件 |
| 显存不足 | 保留失败记录，先减 batch 或禁用非必要后处理；必要时在模型有效范围内减尺寸，并明确记录变化 |
| 自定义节点报错 | 记录节点与版本，检查实际输入和官方兼容性；Anima 的自定义 unsample 节点应检查正负条件是否均连接，不能假设空条件补全可用 |
| 文件成功但角色/机位不符 | 保存为 rejected，回到原始要求修正提示或视觉条件；每次改一个主要变量，创建新版本 |

只操作自己的任务。共享实例上不清 queue/history，不用全局 interrupt 误停别人，也不以服务重启代替排错。

## 4. 验收与记录

每张原图检查格式、实际尺寸、完整解码和 SHA-256，再目视检查身份、服装、肢体、人物数量、构图和背景。没有看图能力就标记“技术检查通过，画面待检查”，不能擅自判定适合视频。

项目台账按 `task_id` 关联：用途与原始要求、输入哈希、模型清单、实际提示词、图与图哈希、所有采样 seed、参数、`prompt_id`、状态、输出哈希、检查结果。运行状态使用 `prepared/submitted/running/succeeded/failed/unknown`，视觉结果另记 `pending/accepted/rejected`。

最终交付原图、推荐用途及简短差异说明。保留项目内可复现原稿；准备公开示例时另做副本，检查 PNG 工作流元数据、文本和文件名，移除个人标识、路径、连接配置及凭据，再发布。
