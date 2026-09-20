# immutable-skill-supply-chain Delta Specification

## MODIFIED Requirements

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
