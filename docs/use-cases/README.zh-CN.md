# Codex Image Factory 使用案例目录

本文档集把已收录上游 Skill 的方法转换成 Image Factory 的真实用户场景。案例不是
复制上游完整提示词，而是说明用户目标如何映射为界面条件、自动处理、交付物和验收。

## 状态标记

- **当前可用**：可通过现有 `prompt-search`、批次计划、run、judge、recover 完成。
- **0.2 目标**：Creative Studio 图片界面与 Creative Director 实施后可用。
- **0.2.1 目标**：参考图视觉 DNA、精确交付尺寸或系列一致性增强后可用。
- **0.3 目标**：本地 FFmpeg 故事视频实施后可用。

## 案例分册

| 分册 | 案例数 | 覆盖内容 |
| --- | ---: | --- |
| [故事、系列与参考图](story-series-reference.zh-CN.md) | 14 | 成语、绘本、漫画、分镜、角色一致性、参考图反推 |
| [社交、电商与品牌](commercial-content.zh-CN.md) | 16 | 小红书、公众号、电商主图、产品营销、品牌触点 |
| [海报、信息图与出版](knowledge-design.zh-CN.md) | 14 | 活动海报、科普、学术图、地图、文档和数据可视化 |
| [角色、UI、游戏与摄影](character-ui-game.zh-CN.md) | 16 | 头像、角色设定、游戏素材、UI、建筑、摄影、纹身稿 |
| [编辑、审阅与视频](edit-review-video.zh-CN.md) | 12 | 局部修改、文字替换、轮次、批准、本地视频与导出 |
| **合计** | **72** | 覆盖所有已归纳能力和目标产品主流程 |

## 22 套结构化模板覆盖

| 模板 ID | 中文名称 | 主要案例编号 |
| --- | --- | --- |
| `ui-screenshot-system` | UI 截图系统 | D07、D08 |
| `infographic-engine` | 信息图引擎 | K05、K06 |
| `scientific-scale-diagram` | 科学尺度缩放图 | K07 |
| `poster-layout-system` | 海报排版系统 | K01、C03 |
| `sports-campaign-poster` | 运动商业 Campaign | C12 |
| `conceptual-typography-poster` | 概念字体海报 | K02 |
| `ink-double-exposure-poster` | 水墨双重曝光海报 | S10 |
| `nature-science-poster` | 自然科普海报 | K03 |
| `product-commerce-visual` | 商品商业视觉 | C07、C08 |
| `personalized-beauty-report` | 个性化美妆报告 | C13 |
| `brand-identity-package` | 品牌身份包 | C14 |
| `brand-touchpoint-board` | 品牌触点视觉板 | C15 |
| `architecture-space` | 建筑与空间 | D12、D14 |
| `realistic-photography` | 写实摄影 | D01、D13 |
| `street-accident-moment` | 街头意外瞬间摄影 | D13 |
| `illustration-art-style` | 插画与艺术风格 | S01、S06、S11 |
| `character-design-sheet` | 角色设定表 | S07、S08 |
| `3d-collectible-toy` | 3D 收藏玩具 | D04 |
| `scene-storytelling` | 场景叙事 | S02、S04、S09 |
| `history-classical-themes` | 历史与古风题材 | S03、S05、S06 |
| `document-publishing` | 文档与出版物 | K14 |
| `concept-product-breakdown` | 概念产品研发拆解 | C16、K13 |

## 31 类图库能力覆盖

| 上游类别 | 本手册案例 |
| --- | --- |
| Anime & Manga | D05、D06 |
| Gaming | D06、D10、D11 |
| Retro & Cyberpunk | C05、S04 |
| Cinematic & Animation | S04、C06 |
| Character Design | S07、S08、D04 |
| Typography & Posters | K01、K02、C03 |
| Illustration | S01、S06、S11 |
| Watercolor | D03、K08 |
| Ink & Chinese | S03、S06、S10 |
| Pixel Art | D10 |
| Isometric | D11 |
| Product & Food | C07、C08、C09 |
| Brand Systems & Identity | C14、C15 |
| Photography | D01、D02、D13 |
| Infographics & Field Guides | K03、K04、K05、K06 |
| Research Paper Figures | K10、K11 |
| Official OpenAI Cookbook Examples | 来源层参考，执行仍遵循当前 Codex 能力；见 K10、E03 |
| Edit Endpoint Showcase | E01、E02、E03、E04 |
| UI/UX Mockups | D07、D08、D09 |
| Data Visualization | K12 |
| Technical Illustration | K11、K13 |
| Architecture & Interior | D12、D14 |
| Scientific & Educational | K03、K07、K09 |
| Fashion Editorial | C08、C11、D02 |
| Fine Art Painting | S06、S11 |
| More Illustration Styles | S01、S05、D03 |
| Cinematic Film References | S04、S12、C06 |
| Beauty & Lifestyle | C13、D01 |
| Events & Experience | C03、K01 |
| Tattoo Design | D15 |
| Screen Photography | D16 |

## 11 类大图库目录覆盖

| 大图库目录 | 本手册案例 |
| --- | --- |
| Profile / Avatar | D01、D02 |
| Social Media Post | C01、C02、C03、C04、C05 |
| Infographic / Edu Visual | K03–K12 |
| YouTube Thumbnail | C06 |
| Comic / Storyboard | S01–S04、S14 |
| Product Marketing | C08、C09、C10、C12、C13 |
| E-commerce Main Image | C07、C08、C09 |
| Game Asset | D05、D06、D10、D11 |
| Poster / Flyer | C03、K01、K02 |
| App / Web Design | D07、D08、D09 |
| Uncategorized / Others | S06、D14、E04 等跨类别需求 |

## 用户应如何查找案例

先按最终交付物找分册，再按编号找相近场景。用户不需要复制案例里的技术词；把自己的
主体、用途、文案、受众和参考图说清楚即可。Creative Studio 会自动选模板和分类，
最多给三个方向，并在生成前展示调用报价。

如果案例需要精确文字、真实商品、人物身份或 Logo，最终确认时要逐项检查。图库中的
案例预览只证明上游案例存在，不证明本插件会得到完全相同的结果。
