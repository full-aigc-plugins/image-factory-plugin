# series-consistency-contract Specification

## Purpose

Make character, object, and style continuity explicit, reproducible generation input for governed image batches.

## Requirements

### Requirement: A series profile SHALL be validated before approval

The Factory SHALL reject unknown entity ids, missing anchor files, invalid reference roles, and more than five effective references for an item before quoting or approval.

#### Scenario: An item names an unknown character

- **WHEN** an item references an entity id absent from the batch profile
- **THEN** plan validation fails without starting a generation call

### Requirement: Effective prompts SHALL materialize continuity constraints

For every item using a series profile, the Factory SHALL deterministically compile the shared style, negative constraints, selected entities, fixed traits, allowed variations, reference roles, and scene request into the prompt consumed by the runner.

#### Scenario: Two frames use the same character

- **WHEN** two items select the same entity
- **THEN** both effective prompts contain the identical fixed entity contract while retaining their different scene requests

### Requirement: Generation identity SHALL bind reference semantics

The idempotency key SHALL bind the effective prompt and ordered reference role, entity id, and content digest. Reclassifying a reference SHALL produce a different key.

#### Scenario: Identity reference becomes layout reference

- **WHEN** the same reference bytes are assigned a different role
- **THEN** the resulting generation idempotency key changes

### Requirement: Rework SHALL retain continuity anchors

The optimizer SHALL carry the profile, entity ids, allowed variations, and references into each selected next-round item.

#### Scenario: One frame is rejected

- **WHEN** a rejected frame receives a rewritten scene prompt
- **THEN** its next-round plan keeps the original series profile and anchor bindings
