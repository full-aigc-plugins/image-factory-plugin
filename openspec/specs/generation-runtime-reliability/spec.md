# generation-runtime-reliability Specification

## Purpose

Attribute every external generation attempt and make its progress and recovery evidence observable without silent retries.

## Requirements

### Requirement: Every attempt SHALL have durable attribution evidence

The runner SHALL persist an attempt id, streamed events, session id when reported, and candidate artifacts before final classification.

#### Scenario: Another process writes an image

- **WHEN** an unrelated image appears in the global generation directory during an active attempt
- **THEN** the Factory does not collect it unless the active session/call evidence attributes it

### Requirement: Progress SHALL be observable without mutation

The CLI SHALL expose current attempt progress from durable event snapshots, and observation SHALL never retry generation.

#### Scenario: A long generation is running

- **WHEN** an operator watches status
- **THEN** new events become visible while the subprocess is still running

### Requirement: Ambiguous completion SHALL recover by attempt

Timeout and interruption SHALL retain their attempt handle. Recovery SHALL search for evidence belonging to that attempt and SHALL NOT start a new generation.

#### Scenario: An artifact arrives after timeout

- **WHEN** the same session publishes a valid artifact after the runner timed out
- **THEN** recovery can collect it and complete the existing attempt without spending another call

### Requirement: Capacity SHALL be checked before external execution

The Factory SHALL reject an approved run before its first external call when the conservative free-space budget is not met.

#### Scenario: Destination space is below the batch budget

- **WHEN** preflight observes less free space than the declared conservative budget
- **THEN** the run stops before invoking Codex and reports the required and available bytes
