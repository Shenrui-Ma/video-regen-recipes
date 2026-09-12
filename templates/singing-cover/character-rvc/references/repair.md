# 哈希护栏、断点恢复与局部修复

两个 helper 都是标准库离线工具，不下载、不发 shell 作业、不载入 checkpoint/NPY/FAISS、不删除用户文件。它们不验证角色、授权、GPU、进程锁或听感，不是大型调度框架。

## 1. run_guard 接口

`snapshot --spec JSON --output 新JSON`：读取实际资源并输出内容指纹；成功退出 0。`check --spec JSON --receipt JSON`：当前输入/参数与 receipt 完全一致退出 0；不一致退出 **1**（stale），输入缺失/格式错误/读写错误退出 **2**。stdout 为简短 JSON，错误 JSON 在 stderr；不要忽略退出码。

spec 格式只有 `schema_version`、`parameters`、`resources` 三项，见 [index-inputs.spec.json](../examples/index-inputs.spec.json)。路径相对 **spec 所在目录**，或使用本机绝对路径；命令 cwd 不改变相对路径语义。运行清单留在私有 job，不提交绝对路径。

```json
{
  "schema_version": 1,
  "parameters": {
    "stage": "index",
    "rvc_commit": "4338f12c3c28c80b3ac015e2d0df66c41592746d",
    "version": "v2",
    "feature_policy": "all-training-source-hubert-no-holdout",
    "n_cpu": 16
  },
  "resources": {
    "features": "index-work/3_feature768",
    "hubert_config": "dependencies/hubert_base/config.json",
    "hubert_weights": "dependencies/hubert_base/pytorch_model.bin",
    "index_source": "source/train_index.py"
  }
}
```

上例路径只是新 job 布局示范，模板不含这些资产。按实际部署绑定，不能创建空文件让检查通过。目录资源递归纳入所有普通文件及其相对成员名、bytes 和 SHA-256；文件资源按 bytes/SHA。增删文件、同大小内容变化、参数变化都会使 fingerprint 变化。只填写 commit 字符串不能证明源码未变，应把实际相关源码和环境 lock 也作为资源。

```bash
python3 "$RECIPES_ROOT/templates/singing-cover/character-rvc/scripts/run_guard.py" snapshot \
  --spec "$JOB/index-inputs.spec.json" --output "$JOB/index-inputs.receipt.json"
python3 "$RECIPES_ROOT/templates/singing-cover/character-rvc/scripts/run_guard.py" check \
  --spec "$JOB/index-inputs.spec.json" --receipt "$JOB/index-inputs.receipt.json"
```

snapshot 不覆盖旧 receipt，父目录必须已存在。拒绝空文件/空资源树、符号链接/特殊文件及位于受检资源中的 receipt（避免自引用 SHA）。上游索引软链接应显式绑定到真实索引文件；不要把整棵仍在变化的 logs 作为已冻结输入。

receipt 没有签名，不是对抗篡改的信任证明；重新 snapshot 只能创建新基线，不能证明旧产物来自新输入。不要对 stale 结果重新签一份当前输入就继续复用旧输出。工具不检测多个进程竞争或哈希期间文件变化，使用时必须持有外部工程锁/独占写权、停止输入写入；此限制和训练同步应由作业所有者保证。

## 2. 怎么证明一个阶段可复用

1. **开始前**：固定新 run ID、角色/语言、上游阶段资源、实际源码、依赖 lock、参数，生成 input receipt；确保无同目录写进程。
2. **执行阶段**：保存实际命令、退出码和日志。训练脚本可能吞掉局部错误，不能仅凭退出 0 判断完成。
3. **执行后**：再次 check input receipt，确保输入没变；解码/检查阶段产物并记录人工关口。用另一份 completion spec 同时绑定本阶段输入、输出和验收记录，生成独立 completion receipt，全部保留。
4. **恢复或启动下游前**：check input 与 completion 两份 receipt；核对原进程是否结束、文件完整性和实际验收状态。任一缺失或失败都不能只凭 marker 或文件名直接跳过。

completion 的参数应记录如 `review_status="pending"` 或具体审听记录 ID，不写自动生成的“权限 true”。receipt 中的输出哈希只能证明检查时字节存在，不证明实际执行与授权成立。

## 3. 各阶段最少绑定项

| 阶段 | 输入/参数 | 完成后额外绑定 |
| --- | --- | --- |
| 预处理 | 筛选清单、train 原片、源分组/区间、源码、48k/per/overlap/阈值 | gt 与 16k 目录、日志、逐片检查报告 |
| F0/HuBERT | 16k 目录、RMVPE/HuBERT 资产与配置、源码、精度/设备参数 | F0/NSF/feature 目录和失败清单 |
| filelist | 四模态、mute、split 清单、helper 源码 | filelist 与报告、数组/音频检查 |
| 训练 | filelist、全部训练模态、底模、config、源码、实际 CLI/环境 | 成功配对 G/D、小模型、训练日志与候选听审 |
| 索引 | 全部冻结索引特征、选择策略、HuBERT 来源、上游源码、参数 | 真实 added 文件、构建日志、d/ntotal 检查 |
| 推理 | 输入分轨、选定小模型、added、共享模型/源码、实参 | 原始转换干声、dtype/缩放/QC 与短段听审 |
| 混音 | 已审听干声、伴奏、对齐参数、FX/增益配置 | aligned、FX、premaster、master、分析和听审 |

## 4. 恢复决策

| 症状 | 先确认 | 允许恢复的最小范围 |
| --- | --- | --- |
| 会话中断/控制链断开 | 原进程、日志进度、正在写的产物、锁归属 | 已完成则只取回核验；未知状态不能重复训练 |
| 预处理 marker 缺失 | source/参数 receipt、真实 gt/16k 与日志 | 不删除旧实验，无法证明一致则新实验重做 |
| 缺一份 F0 | 原 16k/hash、全零音高或提取失败原因 | 同输入时仅补失败项；全零经审查记录排除，不伪造 npy |
| 数据或模型字节变化 | 哪个上游资源改变 | 新版本重做相应特征及下游；旧缓存只读保留 |
| OOM | 原训练是否退出、checkpoint 是否完整 | 降 batch/关闭 cache 的新配置；记录恢复或重启语义 |
| 小模型未导出 | G/D 是否已保存、assets/weights 父目录 | 修目录，用匹配版本导出/下一保存点，不盲目重训 |
| 旧 added 被跳过 | 是否有输入/completion receipt、旧 trained 是否同数据 | 用新索引实验与目录，不能仅更新文件时间或重命名 |
| 转换幅度异常 | dtype、是否 float-PCM16、源信号与固定 API | 修缩放或模型调用，保留异常候选；不自动缩小后当通过 |
| 只有混音不佳 | 审听干声与哈希是否未变 | 只改混音，保留用户手动工程和旧 master |
| QC 环境缺依赖 | 音频是否已完整生成、分析程序是否可用 | 只修 QC/复测，不重新推理歌曲 |

上游训练恢复会寻找 G/D checkpoint，可能在加载失败后走预训练初始化。必须核对**同一步的 G/D、优化器状态、版本/数据/config 和日志中的实际起点**；不能只看最新一个 G 文件或恢复脚本退出 0。只持有小推理模型不能宣称无损恢复优化器训练。需改动数据/配置时使用新实验，明确是新训练还是迁移，不让自动恢复语义替你决定。

## 5. 局部修复与留档

对错字/点击/尾音先修源分轨、F0 或对应声部参数。用父 dry stem 的 SHA 和半开样本区间 `[start_frame,end_frame)` 绑定补丁；转换时带上下文，再在原时间轴裁取、短交叉淡化。保存补丁、交叉区间和新 stem，检查补丁范围外样本不变，之后才重做混音/响度处理；整曲母带归一化会影响全曲，不能在母带层要求范围外字节不变。

直接回填原唱局部音频需要本次用户明确接受并披露，不从旧工程推定已授权。修复前后均听干声和短混音，不能用扩大替换区掩盖错字。

永远保留原件、训练配置与日志、有效清单、关键恢复档、小模型、索引、转换干声、FX、premaster 和人工工程。存储清理由用户独立审查，不在本流程自动删除。哈希清单不要包含清单自身；传输后两端重新算 hash 并完整解码，只传输成功不等于字节一致。
