## Purpose

提供可从已核验回执和评分重建的人工审片工作区，让评审者快速对照基准帧、定位人物和元素差异，并在桌面与移动端完成可追溯标注。

## ADDED Requirements

### Requirement: Review workspace SHALL be rebuildable from verified evidence

审片工作区 SHALL 只引用已核验回执、评分和评审器报告，且 SHALL 能在不调用生成模型、不复制原图、不修改任务台账的情况下重建。

#### Scenario: The review directory is deleted
- **WHEN** 原始回执、图片和评分仍然有效
- **THEN** 系统重建等价的审片索引和页面且不产生生成调用

### Requirement: Reviewers SHALL compare anchors and evidence regions

工作区 SHALL 支持基准帧与当前帧并排查看、人物/服装/道具证据区域定位、按失败维度筛选，并明确区分自动发现与人工标签。

#### Scenario: Character identity is selected
- **WHEN** 评审者筛选 `character_identity`
- **THEN** 页面展示该镜头、对应身份基准和该维度证据，不把其他维度结果混作身份结论

### Requirement: Review workspace SHALL support a 390px viewport

在 390px 宽视口下，核心图片、维度证据、人工接受/拒绝控件和理由输入 SHALL 无水平遮挡且保持可操作。

#### Scenario: A reviewer uses a mobile viewport
- **WHEN** 审片页以 390px 宽度渲染
- **THEN** 基准与当前帧采用可读的纵向布局，决定控件仍可访问
