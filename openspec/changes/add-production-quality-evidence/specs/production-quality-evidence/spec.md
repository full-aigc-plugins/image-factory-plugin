# production-quality-evidence Specification

## Purpose

Provide reviewable, calibrated production evidence for multi-image batches without presenting probabilistic judgments as deterministic truth.

## ADDED Requirements

### Requirement: Quality tiers SHALL remain explicit

Only file-derived checks SHALL fail a deterministic gate. OCR, identity similarity, anatomy, and semantic continuity SHALL remain advisory unless a future approved specification establishes a deterministic contract.

#### Scenario: OCR reports unexpected text

- **WHEN** OCR finds likely readable text in an image with a no-text requirement
- **THEN** the finding is recorded as advisory evidence and does not masquerade as a deterministic file failure

### Requirement: Series review SHALL use closed dimensions

Advisory review SHALL use the declared dimensions `character_identity`, `wardrobe`, `prop_continuity`, `style`, `scene_state`, `text_absence`, and `aspect_ratio`, each with observable evidence.

#### Scenario: Identity score has no observable evidence

- **WHEN** a reviewer returns `character_identity` without naming anchor-to-frame evidence
- **THEN** the dimension is marked incomplete and cannot drive rework

### Requirement: A batch SHALL have a rebuildable visual summary

The Factory SHALL generate a contact sheet and machine-readable storyboard index from verified receipts and evaluation state.

#### Scenario: The visual summary is deleted

- **WHEN** verified receipts and scores still exist
- **THEN** the same summary can be rebuilt without generation calls

### Requirement: Receipts SHALL expose reproducible provenance

Receipts SHALL record the plugin revision, host and Codex versions when observed, capability signature, reviewer version, and consistency profile digest without inventing unavailable values.

#### Scenario: The host version is unavailable

- **WHEN** no reliable host version is observed
- **THEN** provenance records null rather than guessing a value

### Requirement: Advisory quality SHALL be calibratable

The Factory SHALL compare human labels with advisory outcomes and emit dimension-level calibration statistics without silently changing thresholds.

#### Scenario: Human decisions disagree with advisory scores

- **WHEN** accepted and rejected labels contradict the current advisory threshold
- **THEN** the calibration report exposes the disagreements and leaves the configured threshold unchanged
