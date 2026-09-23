# 系列一致性计划指南

image_batch 1.5.0 把人物、道具和画风稳定性从重复文案升级为可校验的生成输入与质量证据，
并新增跨镜头继承的结构化故事状态。
这能降低跨帧漂移，但不承诺底层模型绝对保持身份；最终仍需逐图验收。

## 最小计划

```json
{
  "schema_version": "1.5.0",
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
    ],
    "story_state": {
      "permanent_locks": [
        {"path": "character.amu.hair", "value": "short black hair"},
        {"path": "character.amu.age", "value": "12"}
      ],
      "scenes": [
        {
          "id": "study-room",
          "locks": [
            {"path": "wardrobe.amu", "value": "blue robe with red cloth belt"},
            {"path": "prop.desk", "value": "dark wooden desk"}
          ]
        }
      ],
      "variables": [
        {"path": "prop.book.state", "initial_value": "closed"},
        {"path": "character.amu.pose", "initial_value": "seated"}
      ]
    }
  },
  "items": [
    {
      "id": "scene-01",
      "prompt": "清晨，阿木在窗边练习书法",
      "entity_ids": ["amu"],
      "scene_id": "study-room",
      "allowed_variations": ["姿势", "表情"],
      "references": [{"path": "refs/desk-layout.png", "role": "layout"}]
    },
    {
      "id": "scene-02",
      "prompt": "同一房间里，阿木翻开字帖继续练习",
      "entity_ids": ["amu"],
      "scene_id": "study-room",
      "state_transitions": [
        {"path": "prop.book.state", "from": "closed", "to": "open"}
      ]
    }
  ]
}
```

`consistency_profile` 是共享事实源，不要只把固定特征写进 `goal` 或 `notes`。
验证器会把风格、负向约束、本帧实体、固定特征和允许变化编译进每幅实际 prompt。

`story_state` 将状态分为三层：`permanent_locks` 在整个故事不变，`scenes[].locks`
在指定场次不变，`variables` 只能通过条目级 `state_transitions` 改变。后一镜头没有声明
变化时继承前一镜头状态；`from` 与继承值不一致、修改锁定路径或引用未知场次都会在花费前失败。
优化器只保留失败镜头时，会把已经通过的前序镜头状态压缩成等价转换，因此返工不会让打开的
书重新变回关闭状态。

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
