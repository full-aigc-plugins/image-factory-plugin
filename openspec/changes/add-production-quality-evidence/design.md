## Decisions

1. 宽高比范围与基于固定算法的感知哈希可作为 deterministic gate；OCR、人物相似度、手部异常等模型推断默认 advisory。
2. reviewer 输出采用封闭维度名与证据字段；缺少可观察证据的维度不驱动返工。
3. contact sheet 从已验证回执生成，不重新编码原图；汇总文件是派生物，可重建，不作为完成真相源。
4. receipt provenance 只记录可实际探测的信息；未知值为 null，不推断模型或宿主。
5. 校准报告比较 human label 与 advisory，提供按维度混淆矩阵和阈值候选，但阈值变更仍需独立规格与人工批准。

## Migration Plan

在 v0.5.0 之上先写质量 schema 与派生报告测试，再实现 evaluator、gallery 和 provenance，完成后发布 v0.6.0。
