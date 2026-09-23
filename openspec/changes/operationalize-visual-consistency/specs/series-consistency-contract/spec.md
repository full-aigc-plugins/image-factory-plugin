## ADDED Requirements

### Requirement: A series profile SHALL carry structured story state

系列档案 SHALL 可选声明永久锁定、场次锁定、镜头变量、初始状态和允许的状态路径；条目 SHALL 只声明相对继承状态的显式转换。

#### Scenario: A frame omits unchanged wardrobe
- **WHEN** 后续镜头没有声明服装变化
- **THEN** 该镜头继承当前场次服装锁定并把它编译进有效提示词

### Requirement: Invalid story transitions SHALL fail before approval

未知状态路径、对锁定路径的修改、旧值不匹配、重复路径和未知场次 SHALL 在报价或批准前失败。

#### Scenario: A locked age changes
- **WHEN** 镜头转换尝试修改永久锁定的年龄
- **THEN** 计划验证失败且不开始生成调用
