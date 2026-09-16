# HTML 产品展示动画

**说出产品和卖点，让 Agent 设计一支产品展示动画。**

> 为这个产品做一支 30 秒展示视频，重点表现……，面向……用户。

根据产品特点设计分镜，用 HTML、CSS、SVG 表现操作、对比、流程和结果，交付可修改的网页与 MP4。适用于软件、工具、服务及实体产品；不限定原案例的画风、镜头数或顺序。

示例：[竖屏 ComfyUI 展示动画（B站）](https://www.bilibili.com/video/BV1Qqto6HE8m)。

需要 Node.js、Playwright、Chromium 和 FFmpeg。默认无声；可加入自己的图片、录屏、配音和音乐。

[让 Agent 执行](SKILL.md) · [动画技巧](references/motion-patterns.md) · [制作与导出](references/production.md) · [来源](sources.md)

文件与离线逻辑已检查，公开版未重新渲染或进行视觉验收。

整理：**Shenrui Ma（四倍体果蝇）**。

## 配套资源

- [shenrui-comfyui-toolkit](https://github.com/Shenrui-Ma/shenrui-comfyui-toolkit)：本仓库其它模板使用的固定版本工作流；本模板不调用模型推理
- [Shenrui-Ma/video-regen-assets](https://huggingface.co/datasets/Shenrui-Ma/video-regen-assets)：公开素材库；产品图与字体由用户自备

第三方组件、字体与素材条款见 [LICENSES.md](LICENSES.md)，本次验证范围见 [验证记录](references/validation.md)。
