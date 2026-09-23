# Image Factory 插件技术方案

> **文档信息**
>
> | 字段 | 值 |
> |---|---|
> | 状态 | 0.4.0 release candidate 的已实现方案：新增系列一致性档案、有效 prompt 编译与角色化参考图绑定；真实模型连续性仍需独立运行验收 |
> | 范围 | 技术决策、执行契约、失败模型，以及支撑它们的平台事实 |
> | 读者 | 扩展或评审本插件的实现者 |
> | 运行证据 | `docs/verification/` |
> | 最近一次结构修订 | 2026-09-20 |

[English](Image-Factory-Plugin-Technical-Solution.md) | [简体中文](Image-Factory-Plugin-Technical-Solution.zh_CN.md)

## 1. 技术决策

插件持有确定性状态，把生成与判断交给 Codex。具体来说：

- **本插件不实现生成。** 一个批次项就是一次 `codex exec` 调用，产物就是此后出现在生成目录里的新文件。
- **成功必须有文件。** 退出码为零但没有新图片，会被归类为 `artifact_missing`。
- **改写内容由外部提供，而非本插件生成。** `optimizer.plan_next_round` 决定哪些项要重做，并要求为每一项给出明确指令；文本来自 Codex。
- **参考评分只记录，不遵从。** 由确定性门禁做主判。
- **不重试、不安装、不绕过批准。** 任何地方都不。

另一种方案——由插件自持凭据直接调用图像 API——在本版本被否决：内置通道不需要额外凭据，且只保留一条计费关系，这对第一个版本比"平台本来就不提供的参数控制"更重要。

| 备选方案 | 被否的原因 |
|---|---|
| 由插件自持凭据直接调用图像 API | 多出一条计费关系和一个需要保护的凭据，换来的却是平台本就不提供的参数控制 |
| 按生成器的命名规则预测输出路径 | 输出名来自内部会话与调用 ID，预测会静默失效 |
| 在计划 schema 里接受 `size`、`quality`、`n` 或 `model` | 内置工具一个都不接受；接受它们等于许下无法兑现的承诺 |
| 自动重试失败或含糊的项 | 静默重试就是"一个坏 prompt 变成一张大账单"的成因 |
| 让模型评分决定批次结果 | 判断信号绝不能被静默升级为判决 |

## 2. 仓库布局

```text
.codex-plugin/plugin.json          compatibility manifest
.agents/plugins/marketplace.json   URL marketplace entry
bin/image-factory                  CLI entry point (shim, resolves repo root)
schemas/                           four closed JSON Schemas
scripts/
  schema_lite.py                   schema subset enforcement, stdlib only
  capability_probe.py              offline environment probe
  plan_validator.py                plan validation, idempotency keys, caps
  prompt_library.py                offline attributed prompt discovery
  generation_runner.py             one Codex call per item
  artifact_collector.py            locate, verify, publish, receipt
  job_ledger.py                    durable state machine and schema migration
  job_lock.py                      cross-platform process lock
  receipt_store.py                 atomic per-item receipt source of truth
  evaluator.py                     deterministic gates, advisory, labels
  optimizer.py                     next round planning
  image_factory_cli.py             subcommand wiring and the spend gate
  validate_distribution.py         distribution validator
skills/                            four Agent Skills
data/                              attributed templates and source indexes
vendor/upstream/                   inactive pinned upstream snapshots
tests/                             stdlib unittest suite
docs/                              this document and its pair
```

## 3. 执行契约

每次 Codex 调用都是带 `shell=False` 的 argv 数组：

```text
<codex> exec --json --skip-git-repo-check --color never \
  -C <workdir> -o <last-message-file> [-i <reference>]... <prompt>
```

- `--json` 产出 JSONL 事件流，这是可靠识别用量上限失败的方式，而不是去匹配 stderr 上的散文。
- `-o` 把最终消息写入文件，因此一次运行"自己怎么说"会被保留为证据，但不被当作证明。
- `-i` 附加参考图；平台最多允许五张。
- 工作目录不存在就创建，并同时设为进程工作目录，使相对路径解析可预期。

提示词是"插件固定包装 + 该项有效 prompt"：

```text
Generate exactly one image with the built-in image generation tool. Treat any
attached images as visual references for the result. Do not modify or create any
other file. When you are done, reply with the absolute path of the generated image.

Image description:
<the item's effective prompt>
```

包装是固定的。image_batch 1.3.0 可以声明 `consistency_profile`；验证器按固定顺序把
风格圣经、负向约束、本帧实体、固定特征、允许变化和参考图角色编译成有效 prompt。
实体与风格锚点、条目 `references` 和旧 `reference_images` 合计最多五张。幂等键绑定
有效 prompt 与有序 `(role, entity_id, sha256)`，同一图片从 `identity` 改为 `layout`
会形成新的生成身份。返工轮次深拷贝顶层档案与条目绑定。

回执里的 `prompt_sha256` 精确标识实际有效 prompt。这套契约提高输入稳定性，但不把
底层生成模型的身份一致性描述成确定性保证；逐图对锚评分仍属于 advisory 或人工验收。

## 4. 生成模式

| 模式 | 触发 | 插件做什么 |
| --- | --- | --- |
| Probe | `probe` | 离线读取环境；给出结论与指引。不执行任何东西。 |
| Quote | `quote` | 校验并计数。不花费。 |
| Run | `run --approve` | 生成每个待处理项，为每件产物采集回执。 |
| Resume | 对已有台账执行 `run` | 跳过已有回执的项。 |
| Stop | 触达用量上限 | 记录上限与重置时间；不再尝试任何项。 |

## 5. 测试策略

- **纯逻辑测试。** schema 强制、幂等键派生、门禁评估与状态机都不涉及文件系统或进程活动。
- **假生成器。** `tests/fakes/fake_codex.py` 顶替 `codex exec`，由 JSON 控制文件驱动，因此每条分类路径——成功、生成、失败、用量上限、超时、静默退出——都被确定性地覆盖。
- **可移植的假适配器 shim。** 测试在 Unix 上创建 `sh` 启动器、在 Windows 上创建 `.cmd` 启动器，再执行它来证明参数确实到达假实现。
- **真实产物。** 品牌资产是真实 PNG，因此尺寸、哈希与重复检测是对真实文件测试的，而不是对伪造字节。
- **记录调用。** 假实现会写下收到的 argv，因此测试可以断言 Codex 是如何被调用的，包括断言批准绕过标志并不存在。

完整运行：

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
```

GitHub Actions 在六个格中运行同样的门禁：Ubuntu、macOS 与 Windows，配 Python 3.11 与 3.13。没有任何 job 安装运行时依赖。

## 6. 事务与恢复保证

- `run --approve` 记录一次绑定"已校验计划 SHA-256、当前轮次与剩余项数"的批准。
- 从批准绑定一直到最后一次状态迁移，全程持有基于任务路径的进程锁。抢锁失败的写者在外部调用之前就失败。
- 每次调用之前都会有一次带 `attempt_id` 的原子 `Attempting` 预留。此后被中断即视为结果含糊。
- schema 合法且经哈希校验的逐项回执是完成的唯一事实源；聚合清单由这些回执重建。
- 恢复过程不调用任何生成器。它只推进有回执证明的工作，并把未解决尝试标为 `Unknown`，而常规 run 拒绝重试这类项。
- 旧版 1.0.0 的计划与任务会确定性迁移到 schema 1.1.0，且不伪造批准证据。
- 需要人工标注时，标注缺失会强制 `pending_approval`；模型评估无法越过这道门禁。

## 7. 失败模型

稳定失败码，等宽逗号分隔：

`approval_required`、`artifact_missing`、`capability_unavailable`、`codex_missing`、`duplicate_artifact`、`generation_failed`、`hash_mismatch`、`optimizer_ambiguous_instruction`、`optimizer_empty_rewrite`、`optimizer_missing_instruction`、`optimizer_round_cap_reached`、`optimizer_unexpected_instruction`、`optimizer_unknown_item`、`plan_consistency_profile_required`、`plan_duplicate_entity_id`、`plan_duplicate_item_id`、`plan_empty_prompt`、`plan_exceeds_max_images`、`plan_exceeds_max_rounds`、`plan_missing_reference_image`、`plan_schema_invalid`、`plan_too_many_effective_references`、`plan_unknown_entity`、`plan_unparseable`、`quota_exceeded`、`timeout`、`unknown`。

确定的逐项失败可以继续，并让台账停在 `Partial`。配额失败会停止整批；被中断或结果含糊的调用会停止后续工作并停在 `Unknown`。没有任何结果会导致自动重试。

## 8. 平台事实及其推论

以下事实测自 Codex 源码与开发机上的已安装二进制（2026-09-12）。每条事实都驱动一个具体决策。

| 平台事实 | 它迫使的决策 |
| --- | --- |
| 图像模型固定在 Codex 内且不可选择 | 任何地方都没有模型字段；回执记录 `null` 而不是猜测 |
| 工具只接受 prompt 与参考图 | 批次 schema 省略 `size`、`quality`、`background`、`n`；使用它们的计划会被拒绝 |
| 一次调用产出一张图 | 一个批次是调用的循环，报价统计的是调用数而不是项数 |
| 输出名派生自内部会话与调用 ID | 产物通过目录差分发现，绝不预测路径 |
| 生成会消耗账号的图像额度 | 先报价、再明确批准、然后运行；触达上限即停止整批 |
| 一次编辑最多接受五张参考 | validator 对档案锚点、结构化 `references` 与旧 `reference_images` 的有效合计执行五张上限 |

## 9. 洁净室规则

本仓库基于公开的 Codex 源码树、已发布的插件约定与 `schemas/` 下的 JSON Schema 编写。它不携带任何供应商源码、私有端点或凭据，也不检查或重实现 Codex 内部的图像管线。互操作性完全建立在有文档的 `codex exec` 命令行，以及 Codex 写入用户自己磁盘的文件之上。

## 10. 证据映射

| 断言 | 证据 |
|---|---|
| 执行契约与参数 | `scripts/generation_runner.py`，以及记录 argv 的假实现 |
| 批准绑定与加锁 | `scripts/image_factory_cli.py`、`scripts/job_lock.py` |
| 回执权威 | `scripts/receipt_store.py`、`scripts/artifact_collector.py` |
| 失败分类 | `scripts/generation_runner.py`，以及上文的失败码列表 |
| 台账迁移 | `scripts/job_ledger.py` 与 1.0.0 迁移测试 |
| 平台事实 | 上表，记录于 2026-09-12 |
