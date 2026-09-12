# Codex Image Factory 插件

<img src="assets/logo.png" alt="Codex Image Factory 图标" width="128">

> 面向 Codex 的批量图像生产，每件产物都有可核验的回执。

[English](README.md) | [简体中文](README.zh-CN.md)

## 当前状态

版本 0.1.0 已实现并通过运行期验证。确定性测试、发行检查、插件安装、新会话 Skill 发现以及经授权的两项真实出图证据均记录在 `docs/verification/` 下。

## 项目定位

`codex-image-factory` 把"给定参考图做一批图"变成一次可审计的生产运行：校验批次清单，由 Codex 逐项生成，采集每张产物并独立重算哈希，用确定性门禁评测，再把失败项改写成新一轮 prompt，经你批准后才执行。

```text
Codex -> 校验后的批次清单 -> 内置图像工具 -> 产物采集 + 回执
                                              |
                              确定性门禁 + 参考评分
                                              |
                                  优化后的新一轮 prompt（需批准）
```

插件自身不出图。生成由 Codex 通过其内置图像工具、使用你已有的 Codex 认证完成。

## 平台边界

以下是 Codex 图像工具的实测性质，不是偏好设定；插件围绕它们设计。

- 一批图用哪个图像模型由 Codex 决定，此处不可选择，本仓库也不硬编码、不承诺任何模型名。回执只记录 Codex 告知的内容，未告知时记为 `null`。
- 内置工具只接受 prompt 与参考图。尺寸、质量、背景、张数由 Codex 固定，因此批次项之间的差异只能来自 prompt 与参考图。
- 一次工具调用产出一张图；编辑最多接受五张参考图。
- 出图会消耗当前 Codex 账号的用量额度。插件先估算批次、执行前要求批准，且绝不自动重试。

由于生成不可参数化，需要显式尺寸或质量档位的功能属于**范围之外**而非"计划中"。若日后需要，那是需要独立标注的、由插件自持 API 通道的扩展点；本仓库不新增该通道，也不读取 API Key。

## 工厂补齐的部分

- **批次清单校验** —— 封闭 schema、幂等键、花费前先设硬上限。
- **可核验回执** —— 哈希、大小、尺寸全部从磁盘文件独立重算，并做二次复核以发现验证窗口内被改写的文件。
- **持久台账** —— 原子写、受约束的状态机、密钥清洗，中断后是恢复而不是重复生成。
- **评测** —— 确定性门禁做主判；模型给出的分数仅作参考，同时采集你的批准/驳回标注，用于日后校准该分数。
- **优化即新一轮** —— 失败项被改写成新的 prompt 集合，而不是覆盖上一轮。

## 文档

- [Architecture](docs/Codex-Image-Factory-Plugin-Architecture.md)
- [架构文档](docs/Codex-Image-Factory-Plugin-Architecture.zh_CN.md)
- [Technical solution](docs/Codex-Image-Factory-Plugin-Technical-Solution.md)
- [技术方案](docs/Codex-Image-Factory-Plugin-Technical-Solution.zh_CN.md)
- [设计规格](docs/superpowers/specs/2026-09-12-codex-image-factory-plugin-design.md)
- [实施计划](docs/superpowers/plans/2026-09-12-codex-image-factory-plugin-implementation.md)
- [便携清单迁移说明](docs/portable-migration.md)
- [运行期验证](docs/verification/runtime.md)

## 许可证

Apache-2.0 —— 见 [LICENSE](LICENSE)。
