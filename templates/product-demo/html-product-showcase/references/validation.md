# 验收范围与复测

## 已验证

- 文件与离线逻辑检查：分镜 JSON 结构、渲染脚本参数边界、可 seek 时钟接口（`window.setShotTime(seconds)`）与文档引用关系。
- 离线复测（仓库根目录；Node 侧测试需要 Node 与 Playwright/Chromium）：

```bash
python3 -m unittest discover -s templates/product-demo/html-product-showcase/tests -v
python3 scripts/catalog.py check
```

## 未验证

- 公开版**未重新渲染成片**，未做视觉、动效节奏与字幕安全区验收（status: `adapted-skill-offline-checked-not-rendered`）。
- `runtime.existing_environment_verified=false`，`runtime.clean_install_inference_verified=false`；不调用模型推理，因此没有 GPU 环节。

## 使用者机器仍需完成

装入真实产品图与文案 → 渲染 MP4 → 人工检查动效节奏、字幕安全区、横竖屏重排与音画同步；保留实际参数、字体清单与输出哈希。
