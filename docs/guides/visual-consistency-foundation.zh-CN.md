# 视觉连续性 Foundation

0.7.0 Foundation 把人物和元素稳定性从“提示词写得像不像”推进为三类可验证合同：

1. 结构化故事状态：永久锁定、场次锁定、镜头变量和显式转换。
2. 版本化视觉评审：评审器身份、版本、能力、置信度、不确定度和证据区域。
3. 连续性基准：固定 4/8/12 镜头、逐维人工标签、运行成本与分层指标。

这些合同改善可复现性和可诊断性，但不会承诺底层生成模型绝对保持身份。

## 勤能补拙 4/8/12 镜头基准

仓库提供 `data/benchmarks/diligence-story-{4,8,12}.synthetic.json` 三组固定故事包。它们覆盖正面、侧面、近景、
远景、遮挡、白天、夜晚和情绪变化，但其 `evidence_tier` 是 `synthetic`：这是合同与
聚合器测试数据，不是真实模型验收。

完成一次有人工标签的 run 后，可离线聚合：

```bash
bin/image-factory benchmark \
  --pack data/benchmarks/diligence-story-4.synthetic.json \
  --run benchmark-runs/run-001.json \
  --out benchmark-report.json \
  --json
```

命令不读取任务台账、不调用 Codex，也不消耗图像额度。报告包含：

- 一次通过率和平均返工轮次；
- 人物身份漂移率与核心道具丢失率；
- 六个人工维度的已标注、未标注、拒绝数量；
- 已观察到的成本和耗时；
- 按 model、provider、prompt strategy 的分层结果；
- `sufficient` 或 `insufficient_sample`，单次完美运行仍不能建立总体稳定性结论。

成本或耗时无法观察时必须是 `null`，不能用零伪装成免费或瞬时完成。

## 版本化 reviewer report

```json
{
  "schema_version": "1.0.0",
  "batch_id": "diligence-story",
  "round": 1,
  "reviewer": {
    "id": "local-identity-reviewer",
    "version": "1.2.0",
    "capabilities": ["identity_embedding", "wardrobe_similarity"],
    "model": null,
    "provider": null,
    "confidence_threshold": 0.7
  },
  "items": [
    {
      "item_id": "frame-01",
      "findings": [
        {
          "dimension": "character_identity",
          "score": 0.72,
          "confidence": 0.65,
          "evidence": "下颌轮廓与身份基准存在差异",
          "region": {"x": 0.2, "y": 0.1, "width": 0.3, "height": 0.4}
        }
      ]
    }
  ]
}
```

该 finding 会被保存为 `uncertain`，供人工复核和后续校准使用，但不会单独驱动返工。

## 尚未完成的证据

- aHash/dHash/pHash 组合策略、置信区间与漂移监控仍在 P1。
- 基准帧对照、局部放大、390px 人工审片工作区仍在 P1。
- 真实付费 4/8/12 镜头、跨宿主/模型和故障注入矩阵仍在 P2，状态必须保持 `NOT_RUN`。
