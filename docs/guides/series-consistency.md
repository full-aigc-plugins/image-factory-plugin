# 系列一致性计划指南

image_batch 1.3.0 把人物、道具和画风稳定性从重复文案升级为可校验的生成输入。
这能降低跨帧漂移，但不承诺底层模型绝对保持身份；最终仍需逐图验收。

## 最小计划

```json
{
  "schema_version": "1.3.0",
  "batch_id": "diligence-story",
  "round": 1,
  "consistency_profile": {
    "mode": "series",
    "style_bible": "温暖中国水彩绘本，柔和纸张纹理",
    "negative_constraints": ["不要可读文字", "不要改变服装颜色"],
    "style_reference_images": ["refs/style.png"],
    "entities": [
      {
        "id": "amu",
        "kind": "character",
        "description": "勤奋但起步较慢的少年学徒",
        "fixed_traits": ["圆脸", "蓝色短袍", "红布腰带"],
        "reference_images": ["refs/amu.png"]
      }
    ]
  },
  "items": [
    {
      "id": "scene-01",
      "prompt": "清晨，阿木在窗边练习书法",
      "entity_ids": ["amu"],
      "allowed_variations": ["姿势", "表情"],
      "references": [{"path": "refs/desk-layout.png", "role": "layout"}]
    }
  ]
}
```

`consistency_profile` 是共享事实源，不要只把固定特征写进 `goal` 或 `notes`。
验证器会把风格、负向约束、本帧实体、固定特征和允许变化编译进每幅实际 prompt。

## 参考图角色

- `identity`：人物或主体身份。
- `style`：笔触、材质和配色。
- `prop`：必须保持造型的道具或元素。
- `layout`：构图和空间关系。
- `edit_target`：需要基于其修改的目标图。
- `generic`：旧计划或无更精确语义的参考图。

档案锚点、结构化 `references` 和旧 `reference_images` 合计最多五张。路径顺序、角色、
实体 id 与文件摘要都会绑定幂等键；同一文件改成不同角色会形成新的生成请求。

## 返工规则

返工只改条目的场景 `prompt`。`optimize` 会保留 `consistency_profile`、`entity_ids`、
`allowed_variations` 和参考图；如果这些约束本身需要改变，应把它视为新批准输入。

先执行：

```bash
bin/image-factory validate-plan image-plan.json
bin/image-factory quote image-plan.json --json
```

报价结果会显示 `consistency_mode`、`consistency_profile_sha256` 和每项有效参考图数量。
