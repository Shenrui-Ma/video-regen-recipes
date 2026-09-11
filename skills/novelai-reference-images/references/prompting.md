# 提示词与验收

以下是本仓库的工作方法，示例不绑定角色、画师或私人风格。

## 先填一张图片任务卡

| 字段 | 要填什么 |
|---|---|
| 用途 | 身份参考 / 场景设计 / 首帧 / 中间帧 / 尾帧 |
| 固定内容 | 发型、瞳色、服装结构、配饰位置、画风 |
| 本张变化 | 姿态、表情、机位、景别、视线 |
| 场景 | 人物在画面中的位置、环境、光向、时间 |
| 交付 | 宽高、文件名、下游镜头编号 |
| 成功条件 | 必须可见的细节、不能裁掉的部位、不能改变的内容 |

身份图优先清楚展示设计；镜头关键帧需要符合实际构图。不要把多视图设定表直接当作单镜头首帧，除非下游明确要求。

## 写法

正向内容按“画面人数与景别 → 固定特征和服装 → 动作表情 → 场景与光线 → 构图要求”排列。把长期角色描述保存在项目中，各张只改镜头部分。不要不经用户要求塞入作品名、画师名或大段质量标签。

```text
single adult character, full body, standing in a neutral pose,
short dark hair, green eyes, plain blue jacket, gray trousers,
hands relaxed at sides, front view, simple light background,
clean linework, balanced lighting, entire body visible, no text
```

负向内容针对当前失败，例如 `cropped feet, duplicate person, unreadable text`。正负向不能同时要求同一元素出现与消失。不要堆砌“绝对一致”等承诺性词语。

图生图仍需描述要保留的可见内容；`strength` 越低通常越接近底图，但不是像素锁定。[官方图生图说明](https://docs.novelai.net/en/image/controltools/)

V4/V4.5 的标签和语言约束与 V5 不完全相同。选定模型后查对应官方说明；不要将某代提示词格式直接复制到另一代。结构化多角色提示中，基础场景和各人物描述分开；使用坐标时核对对应人物。API 请求的平铺提示词和结构化提示词必须同步修改。[官方模型说明](https://docs.novelai.net/en/image/models/) · [多角色提示](https://docs.novelai.net/en/image/multiplecharacters/)

## 图片到视频的交接

1. 打开实际文件检查，不靠文件名或模型自评：人数、身份特征、固定服装、关键配饰、手脚和画面裁切。
2. 对照相邻关键帧：左右方向、视线、人物大小、镜头轴线、光向与道具状态是否连续。
3. 不符合时写出一个可定位问题，再调整提示词、底图或参考强度；种子固定便于比较，不保证服务升级后逐像素一致。
4. 用户项目保存：镜头编号、用途、输入图 SHA-256、实际请求、输出 SHA-256、验收结果。公开分享前检查图片元数据和项目文件是否含私有提示词或素材信息。
