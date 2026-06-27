# Architecture Decision Records (ADR)

This directory holds **Architecture Decision Records** — the third level of the
project's documentation hierarchy (PROJECT.md, section 17):

```
PROJECT.md  →  ARCHITECTURE.md  →  ADR  →  Implementation (Code)
```

An ADR answers **"why was this architectural decision made?"**. After the three
architectural charters were accepted, all significant architectural changes must
be recorded as ADRs (PROJECT.md, sections 11 and 17).

## How it works

- Each decision is one Markdown file named `NNNN-short-title.md`, where `NNNN`
  is a zero-padded, monotonically increasing number.
- Start from [`0000-adr-template.md`](0000-adr-template.md).
- An ADR is immutable once **Accepted**. To change a decision, write a new ADR
  and mark the old one `Superseded by ADR-XXXX`.
- ADRs are versioned and reviewed exactly like code.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-stage-1-tooling-and-project-scaffold.md) | Stage 1 tooling and project scaffold | Accepted |
| [0003](0003-run-domain-model-interface-contract.md) | Run domain model interface contract | Accepted |
| [0004](0004-task-aggregate-run-task-interface-contract.md) | Task aggregate — Run↔Task interface contract | Accepted |
| [0005](0005-output-entity-interface-contract.md) | Output entity — Run/Task↔Output interface contract | Accepted |
| [0006](0006-artifact-entity-interface-contract.md) | Artifact entity — Run↔Artifact interface contract | Accepted |
| [0007](0007-human-review-and-artifact-publication-path.md) | Human Review entity + the Artifact approval/publication path | Accepted |
| [0008](0008-schema-entity-interface-contract.md) | Schema entity — interface contract + Output validation path | Accepted |
| [0009](0009-workflow-and-workflow-step-declarative-contract.md) | Workflow + Workflow Step — declarative interface contract | Accepted |
