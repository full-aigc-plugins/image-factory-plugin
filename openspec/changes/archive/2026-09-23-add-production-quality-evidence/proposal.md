## Why

现有确定性检查只覆盖文件、PNG、尺寸、hash、重复和少量像素规则；人物一致性、意外文字、比例漂移和近似重复只能依赖自由格式 advisory。批次也缺少一眼可审的 contact sheet 与完整环境溯源。

## What Changes

- 引入结构化系列质检维度：人物身份、服装、道具、画风、场景状态、文字缺失和构图比例。
- 增加 OCR、宽高比范围与感知哈希近重复检查；外部/模型判断保持 advisory，确定算法才可成为硬门禁。
- 生成 contact sheet 与故事板清单，逐项显示状态、轮次、锚点和评审结论。
- 回执记录插件 commit、宿主、Codex 版本、能力签名、reviewer 版本与一致性档案摘要。
- 保存 human label 与 advisory 的校准数据，输出误报/漏报统计，不自动重写阈值。

## Capabilities

### New Capabilities

- `production-quality-evidence`: 定义系列质检、预览汇总、质量校准和 provenance。

## Impact

影响 evaluator、review contract、receipt schema、CLI report、文档和测试；依赖前两个增量版本。
