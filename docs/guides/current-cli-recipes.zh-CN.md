# 当前版本 CLI 实操手册

> 适用于当前 0.1.1 图片内核和提示词检索。Creative Studio 图形界面、
> 参考图视觉 DNA 和本地故事视频仍按实施计划推进。

## 1. 查找提示词方向

```bash
bin/image-factory prompt-search '成语绘本分镜' --limit 3 --json
```

结果包含模板、命中词、来源提交、许可证和相关分类入口。`rank_score` 是关键词命中数，
不是图像质量分。没有匹配时返回空数组，不会编造案例。

常用查询：

```bash
bin/image-factory prompt-search '小红书知识封面' --limit 3 --json
bin/image-factory prompt-search '茶叶电商产品海报' --limit 3 --json
bin/image-factory prompt-search '儿童水墨故事分镜' --limit 3 --json
bin/image-factory prompt-search '科技信息图' --limit 3 --json
```

## 2. 准备批次计划

当前版本仍使用 JSON 计划。每项只接受 `id`、`prompt`、最多五张参考图和可选 notes。
不要加入 `model`、`size`、`quality`、`background` 或 `n`。

```json
{
  "schema_version": "1.0.0",
  "batch_id": "idiom-story-001",
  "round": 1,
  "goal": "制作四幅亡羊补牢课堂插画",
  "limits": {
    "max_images": 4,
    "max_rounds": 2,
    "require_approval_before_run": true
  },
  "judge_policy": {
    "min_dimension": 512,
    "reject_duplicates": true,
    "pass_threshold": 0.8,
    "advisory_enabled": true,
    "require_human_labels": true
  },
  "items": [
    {"id": "scene-01", "prompt": "古代牧羊人清晨查看完整羊圈，儿童绘本插画，无文字。"},
    {"id": "scene-02", "prompt": "同一牧羊人发现羊圈破洞和丢失的羊，保持服饰与场景一致，无文字。"},
    {"id": "scene-03", "prompt": "同一牧羊人检查破洞并准备木材，动作清楚，保持画风一致，无文字。"},
    {"id": "scene-04", "prompt": "同一牧羊人修好羊圈，羊群安全归圈，温暖收束，无文字。"}
  ]
}
```

把共享人物、服饰、地点、道具、画笔和配色约束重复写入系列项。当前系统不会自动从
第一项继承未写出的条件。

## 3. 校验与报价

```bash
bin/image-factory validate-plan plan.json --json
bin/image-factory quote plan.json --json
```

只有校验成功的计划才能运行。报价显示 `image_count`，一项对应一次图片生成调用；
报价本身不消耗图片额度。

## 4. 批准并生成

```bash
bin/image-factory run \
  --plan plan.json \
  --job job.json \
  --destination out/ \
  --approve \
  --json
```

`--approve` 表示用户已看过本轮数量并同意运行。命令不会自动重试。只有生成目录出现
新文件并通过采集校验，项目才记为 `Generated`。

## 5. 查看状态与恢复

```bash
bin/image-factory status --job job.json --json
```

`Running` 表示上次运行未正常结束；再次运行前先查看每项状态。已有回执的项会跳过，
已经失败的项不会偷偷重试。`Partial` 需要先读失败分类，再决定是否建立新轮次。

## 6. 确定性评测

```bash
bin/image-factory evaluate \
  --plan plan.json \
  --job job.json \
  --scores scores.json \
  --destination out/ \
  --json
```

评测检查文件、PNG、尺寸、哈希和重复内容。模型建议分属于 advisory，不替代这些门禁。

## 7. 写入人工批准

准备 `labels.json`：

```json
{
  "scene-01": "approved",
  "scene-02": "approved",
  "scene-03": "rejected",
  "scene-04": "approved"
}
```

然后重新评测：

```bash
bin/image-factory evaluate \
  --plan plan.json \
  --job job.json \
  --scores scores.json \
  --destination out/ \
  --labels labels.json \
  --json
```

人工 rejected 会使该项需要调整，即使确定性门禁和建议分都通过。

## 8. 只重做选中项

为需要修改的项准备 `rewrites.json`：

```json
{
  "scene-03": "保持同一牧羊人的脸型、服饰和羊圈位置；让修补木板的动作更明确，画面中不要出现第二个人。"
}
```

```bash
bin/image-factory optimize \
  --plan plan.json \
  --scores scores.json \
  --rewrites rewrites.json \
  --out plan-round-2.json \
  --json

bin/image-factory validate-plan plan-round-2.json --json
bin/image-factory quote plan-round-2.json --json
```

新计划不会修改上一轮。再次运行前仍需批准新报价。环境失败且 prompt 无须变化时，
使用 `--retry-unchanged scene-id` 明确记录决定。

## 9. 使用参考图

在单项加入：

```json
{
  "id": "scene-02",
  "prompt": "保持参考图人物的脸型、发型、蓝灰布衣和体型，画面改为发现羊圈破洞。",
  "reference_images": ["/absolute/path/character-reference.png"],
  "notes": "reference role: subject and costume"
}
```

最多五张参考图。prompt 里要写清每张图是主体、风格、构图、Logo 还是编辑目标，不能
只附图片而不说明用途。

## 10. 当前边界

- 当前没有图形化条件选择界面。
- 当前不会自动从一句目标生成完整计划。
- 当前图片生成尺寸由 Codex 内置工具决定。
- 当前没有本地视频渲染命令。
- 当前不调用外部生图 API，也不读取 API Key。

目标体验和实施顺序见[Creative Studio 设计规格](../superpowers/specs/2026-09-13-codex-creative-studio-design.md)
和[实施计划](../superpowers/plans/2026-09-13-codex-creative-studio-implementation.md)。
