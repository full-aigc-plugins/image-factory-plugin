# 生产质量证据

Image Factory 把“文件事实”和“视觉判断”分开，避免把模型判断伪装成确定性真相。

## 两层质量门禁

- deterministic：文件存在、PNG、最小尺寸、哈希、声明式像素检查、逐项宽高比范围、
  固定 `average-hash-8x8-luma-v1` 的近重复距离。
- advisory：人物身份、服装、道具连续性、画风、场景状态、无文字与视觉宽高比判断。
  OCR、手部/解剖和语义连续性也只能进入这一层。

系列条目的评审维度名是封闭的：`character_identity`、`wardrobe`、
`prop_continuity`、`style`、`scene_state`、`text_absence`、`aspect_ratio`。
每个维度必须给出能在画面中指出的 evidence；空 evidence 会被记录为 incomplete，不能
驱动返工。

## 计划声明

```json
{
  "schema_version": "1.5.0",
  "judge_policy": {
    "min_dimension": 512,
    "reject_duplicates": true,
    "near_duplicate_hamming_distance": 4,
    "pass_threshold": 0.8,
    "advisory_enabled": true,
    "require_human_labels": true
  },
  "items": [
    {
      "id": "frame-01",
      "prompt": "学生在灯下练字",
      "aspect_ratio_range": {"min": 0.95, "max": 1.05}
    }
  ]
}
```

近重复阈值缺省时不启用感知哈希门禁，以保持旧计划行为。阈值越大，越多相似图会被
判为近重复；它只比较固定算法哈希，不声称理解人物身份或语义。

## 派生物与重建

`evaluate` 写出 scores、`*.calibration.json`、`contact-sheet.html` 与
`storyboard.json`。HTML 直接引用已核验原图，不重新编码，也不复制图片。删除派生汇总后：

```bash
bin/image-factory summarize \
  --plan plan.json --job job.json --scores scores.json \
  --destination out --out-dir review-summary --json
```

`summarize` 只读取已核验回执和评分，不调用 Codex、不消耗图片额度、不修改任务台账。
校准报告展示人工标签与 advisory 的混淆矩阵、分维度一致/分歧数量和候选阈值；
`threshold_changed` 固定为 `false`，任何阈值调整都需要独立规格和人工批准。

## 证据边界

回执中的 provenance 只保存实际观察到的 revision、宿主/Codex 版本、能力签名、reviewer
版本和一致性档案摘要。无法观察时写 `null`，不填“看起来合理”的值。单元测试可以证明
合同与算法，不等于真实模型已通过人物连续性验收；后者仍需在磁盘与额度允许时用真实批次
逐图验收。

## 版本化视觉评审器

`evaluate --reviewer-report reviewer.json` 接受带 reviewer id、版本、能力集合、置信度和
可观察证据的标准报告。低于报告 `confidence_threshold` 的 finding 会保留为
`uncertain`，但不会进入返工分数；原始 finding、证据区域和来源仍写入 scores 1.3.0。
多份报告可重复传入 `--reviewer-report`，派生 advisory 只聚合高置信度 finding，原始报告
不会被覆盖。评审器始终是 advisory，不能制造确定性失败，也不能推翻人工决定。
