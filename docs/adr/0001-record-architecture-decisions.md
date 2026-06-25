# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-25
- **Deciders:** Lead Architect

## Context

`PROJECT.md` (sections 11 and 17) establishes a documentation hierarchy in which
**ADRs** are the place where individual architectural decisions and their
rationale are recorded. After the charters (`PROJECT.md`, `ARCHITECTURE.md`,
`ROADMAP.md`) are accepted, further architectural changes are allowed **only**
through ADRs. We need a lightweight, durable process to capture those decisions.

## Decision

We will record every significant architectural decision as an ADR in
`docs/adr/`, using the lightweight Nygard-style template
([`0000-adr-template.md`](0000-adr-template.md)). ADRs are numbered, immutable
once accepted, superseded rather than rewritten, and reviewed like code.

## Consequences

### Positive

- Decisions and their reasons are traceable and survive team turnover.
- The charters stay clean: detail and rationale live in ADRs.
- Reviews have an explicit place to challenge or legalise deviations.

### Negative / Trade-offs

- Small ongoing discipline cost: each architectural change needs an ADR.

## Alternatives considered

- **No formal record (decisions in commit messages / chat)** — not durable,
  not discoverable, contradicts `PROJECT.md` sections 11 and 17.
- **A single growing "decisions" document** — harder to review per-decision and
  to mark supersession cleanly.

## References

- `PROJECT.md` sections: 11 (version control / ADR), 17 (documentation hierarchy)
