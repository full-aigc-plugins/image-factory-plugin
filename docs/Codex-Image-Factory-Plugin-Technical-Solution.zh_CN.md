# Codex Image Factory 插件技术方案

> 0.1.2 release candidate（发布候选）的已实现技术方案，更新日期 2026-09-14；外部发布门禁尚未运行。

[English](Codex-Image-Factory-Plugin-Technical-Solution.md) | [简体中文](Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md)

## 1. 技术决策

插件持有确定性状态，把生成与判断交给 Codex。具体来说：

- **生成不在此实现。** 一个批次项就是一次 `codex exec` 调用，产物是调用之后生成目录里出现的新文件。
- **成功必须有文件。** 退出码为 0 但没有新图像，一律归类为 `artifact_missing`。
- **改写是外部提供的，不是生成的。** `optimizer.plan_next_round` 决定哪些项要重做，并要求每项都有显式指令；文本本身来自 Codex。
- **参考分只记录，不执行。** 判定由确定性门禁做出。
- **不重试、不安装、不绕开审批。** 任何位置都不例外。

被否决的替代方案是：由插件自持凭证直连图像 API。本版不采用，因为内置通道不需要任何额外凭证、只维持一段计费关系；对首个版本而言，这一点比"平台本来就不提供的参数控制"更重要。

## 2. 目标目录

```text
.codex-plugin/plugin.json          兼容清单
.agents/plugins/marketplace.json   URL marketplace 条目
bin/image-factory                  CLI 入口（shim，自行解析仓库根）
schemas/                           四份封闭 JSON Schema
scripts/
  schema_lite.py                   schema 子集执行器，仅标准库
  capability_probe.py              离线环境探测
  plan_validator.py                清单校验、幂等键、上限
  prompt_library.py                离线提示词检索与来源归属
  generation_runner.py             每项一次 Codex 调用
  artifact_collector.py            定位、核验、发布、回执
  job_ledger.py                    持久状态机与 schema 迁移
  job_lock.py                      跨平台进程锁
  receipt_store.py                 原子逐项回执事实源
  evaluator.py                     确定性门禁、参考分、标注
  optimizer.py                     下一轮计划
  image_factory_cli.py             子命令装配与花费门禁
  validate_distribution.py         发行校验器
skills/                            四个 Agent Skill
data/                              带来源的模板与分类索引
vendor/upstream/                   非活跃固定上游快照
tests/                             351 个测试，标准库 unittest
docs/                              本文档及其配对版本
```

## 3. 执行契约

每次 Codex 调用都是 argv 数组，`shell=False`：

```text
<codex> exec --json --skip-git-repo-check --color never \
  -C <workdir> -o <last-message-file> [-i <reference>]... <prompt>
```

- `--json` 产出 JSONL 事件流，用量超限因此能被可靠识别，而不是靠匹配 stderr 上的散文描述。
- `-o` 把最终消息写入文件，使一次运行对自身的陈述作为证据留存，但不被当作证明。
- `-i` 附加参考图；平台最多允许五张。
- 工作目录不存在时会被创建，同时设为进程工作目录，使相对路径可预期解析。

prompt 由插件的固定包装段加批次项自身的 prompt 组成：

```text
Generate exactly one image with the built-in image generation tool. Treat any
attached images as visual references for the result. Do not modify or create any
other file. When you are done, reply with the absolute path of the generated image.

Image description:
<批次项自身的 prompt>
```

包装段固定不变，因此作者写的 prompt 是一次请求中唯一可变的部分，回执里的 `prompt_sha256` 也就精确标识了当时的要求。

## 4. 运行模式

| 模式 | 触发 | 插件行为 |
| --- | --- | --- |
| 探测 | `probe` | 离线读取环境，输出判定与指引。不执行任何程序。 |
| 报价 | `quote` | 校验并计数。不产生任何花费。 |
| 运行 | `run --approve` | 逐项生成，每件产物采集一份回执。 |
| 恢复 | 对已有台账执行 `run` | 跳过已有回执的项。 |
| 停止 | 用量超限 | 记录限额与重置时间，不再尝试后续任何项。 |

## 5. 测试策略

- **纯逻辑测试。** schema 执行、幂等键推导、门禁判定、状态机，全程不触碰文件系统或进程。
- **假生成器。** `tests/fakes/fake_codex.py` 代替 `codex exec`，由 JSON 控制文件驱动，因此成功、出图、失败、用量超限、超时、静默退出等每条分类路径都能确定性地覆盖。
- **可移植假适配器 shim。** 测试在 Unix 创建 `sh` 启动器、在 Windows 创建 `.cmd` 启动器，并实际执行以证明参数到达 fake。
- **真实产物。** 品牌资产是真实 PNG，因此尺寸、哈希与重复检测是针对真实文件测试的，而不是伪造的字节。
- **记录调用。** fake 会写下它收到的 argv，测试因此能断言 Codex 被如何调用，包括审批绕过类 flag 确实缺席。

运行方式：

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -v
python3 scripts/validate_distribution.py .
git diff --check
```

GitHub Actions 用六个单元运行同一组门禁：Ubuntu、macOS、Windows 分别搭配 Python 3.11 与 3.13，且不安装任何运行时依赖。

## 6. 事务与恢复保证

- `run --approve` 把批准记录绑定到已校验计划的 SHA-256、当前轮次与剩余项数。
- 从作业路径派生的进程锁覆盖批准绑定到最终状态迁移；竞争失败的写者在外部调用前退出。
- 每次调用前先原子记录带 `attempt_id` 的 `Attempting`；此后中断即具有歧义。
- 符合 schema 且哈希核验通过的逐项回执是完成事实源；聚合清单由这些回执重建。
- 恢复绝不调用生成器，只提升有回执证明的工作，并把未解决尝试标记为 `Unknown`；普通运行拒绝重试它。
- 旧 1.0.0 计划与作业确定性迁移到 schema 1.1.0，且不虚构批准证据。
- 需要人工标注时，标签缺失强制产生 `pending_approval`，模型参考意见不能越过该门禁。

## 7. 失败模型

稳定的错误码全集（等宽，逗号分隔）：

`approval_required`, `artifact_missing`, `capability_unavailable`,
`codex_missing`, `duplicate_artifact`, `generation_failed`, `hash_mismatch`,
`optimizer_ambiguous_instruction`, `optimizer_empty_rewrite`,
`optimizer_missing_instruction`, `optimizer_round_cap_reached`,
`optimizer_unexpected_instruction`, `optimizer_unknown_item`, `plan_duplicate_item_id`,
`plan_empty_prompt`, `plan_exceeds_max_images`, `plan_exceeds_max_rounds`,
`plan_missing_reference_image`, `plan_schema_invalid`, `plan_unparseable`,
`quota_exceeded`, `timeout`, `unknown`。

确定性的单项失败可以继续，并让台账落在 `Partial`。用量超限会终止批次；调用中断或其他歧义结果会停止后续工作并留下 `Unknown`。任何结果都不会触发自动重试。

## 8. 平台事实与由此产生的决定

以下事实测自 Codex 源码与开发机上的已安装二进制（2026-09-12）。每条事实都对应一个具体决定。

| 平台事实 | 它迫使的决定 |
| --- | --- |
| 图像模型在 Codex 内固定，不可选择 | 任何位置都不设模型字段；回执记录 `null` 而非猜测 |
| 工具只接受 prompt 与参考图 | 批次 schema 不设 `size`、`quality`、`background`、`n`；使用它们的计划会被拒绝 |
| 一次调用产出一张图 | 批次是调用循环，报价统计的是调用次数而非项数 |
| 输出名派生于内部会话与调用 id | 产物通过目录差分定位，绝不用预测路径 |
| 出图消耗账号图像额度 | 报价 → 显式批准 → 运行；超限即停止批次 |
| 编辑最多接受五张参考图 | schema 把 `reference_images` 限制为五 |

## 9. Clean-room 规则

本仓库依据公开的 Codex 源码树、已发布的插件约定与 `schemas/` 中的 JSON Schema 编写。它不内联任何厂商源码、私有端点或凭据，也不检查或重实现 Codex 内部的图像流水线。互操作性完全建立在有文档的 `codex exec` 命令行，以及 Codex 写入用户自有磁盘的文件之上。
