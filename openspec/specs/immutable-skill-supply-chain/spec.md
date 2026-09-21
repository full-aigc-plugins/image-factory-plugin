# immutable-skill-supply-chain Specification

## Purpose
确保插件安装的外部技能只来自不可变且可验证的正式发布，并通过 release tag、peeled commit SHA、内容摘要和本地技能清单建立可审计的供应链；同时允许少量明确声明的插件专属技能安全共存，而不被外部同步覆盖。
## Requirements
### Requirement: External skills are immutable and verifiable
插件 MUST 以 release tag、peeled commit SHA 和内容摘要锁定每个受管技能，检查命令 MUST 在 ref 移动、内容篡改、技能缺失或摘要不一致时失败。

#### Scenario: Managed skill content is unchanged
- **WHEN** 对已同步插件运行在线或离线完整性检查
- **THEN** 所有受管技能的来源、提交和内容摘要均与锁文件一致

#### Scenario: Managed content is tampered
- **WHEN** 已锁定的受管技能文件被修改、删除或其 tag 指向不同提交
- **THEN** 完整性检查以非零状态失败且不静默重写锁文件

### Requirement: Plugin-local skills are explicit
插件 MUST 通过声明式清单列出插件专属技能，vendor 更新 MUST 保留已声明的本地技能并拒绝未声明的额外技能目录。

#### Scenario: Declared plugin-local skill exists
- **WHEN** vendor 更新受管技能
- **THEN** 已声明的插件专属技能保持不变并继续被三端发现

#### Scenario: Undeclared skill appears
- **WHEN** `skills/` 中出现既不受锁管理也未列入本地清单的目录
- **THEN** 更新或检查命令失败并指出该目录

### Requirement: Upgrade events identify exact source state

Skill upgrade events MUST identify the locked package, immutable release tag, and peeled commit SHA. The plugin sync workflow MUST reject unknown packages and MUST verify the tag resolves to the dispatched commit before updating files.

#### Scenario: Valid release event arrives for one of multiple sources

- **WHEN** a trusted skill repository dispatches `package`, `ref`, and matching `sha`
- **THEN** the plugin updates only that package's lock entry and managed skill directories and creates a reviewable upgrade change

#### Scenario: Valid release event arrives

- **WHEN** a trusted skill repository publishes a release and provides a matching package, tag, and commit
- **THEN** the plugin generates a reviewable change containing only the expected managed skills, lockfile update, and required release metadata

#### Scenario: Event omits package for the legacy source

- **WHEN** the existing `image-factory-skills` producer sends the historical `ref` and `sha` payload without `package`
- **THEN** the workflow selects `image-factory-skills` for backward compatibility

#### Scenario: Event names an unknown package

- **WHEN** the payload package is not present in `skills.lock.json`
- **THEN** the sync command fails without changing managed skills or the lockfile

#### Scenario: Event commit does not match tag

- **WHEN** the dispatched commit differs from the remote tag's peeled SHA
- **THEN** the sync workflow fails without modifying plugin skills or the lockfile

### Requirement: Release surfaces remain consistent
发布前验证 MUST 确认 Codex、ZCode、Kimi manifest、市场版本、插件 tag 和测试结果属于同一发布。

#### Scenario: Release candidate is consistent
- **WHEN** 发布候选通过分发检查
- **THEN** 三端 manifest 版本一致，受管技能检查通过，插件 tag 与 GitHub Release 可对应到同一 commit

