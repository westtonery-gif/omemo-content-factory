# ADR-0007: Human Review entity + the Artifact approval/publication path

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** Lead Architect / Domain Architect

## Context

`Human Review` is the mandatory human approval at the Approval Gate (`DOMAIN_MODEL.md` §2.14,
§9.1, §10; `PROJECT.md` §12) — the architectural invariant that **nothing is published without
an explicit human `Approve`**. It is a child entity of the `Run` aggregate root. It was deferred;
this ADR defines its interface contract and the **coupling that lets an Artifact reach
`PUBLISHED` only after an approving Human Review** (`DOMAIN_MODEL.md` §6: "Ни один Artifact не
получает статус `Published` без предшествующего `Approve`").

This unblocks an approval-gated delivery pipeline (e.g. publishing to Telegram **after** human
approval). It mirrors ADR-0004/0005/0006 and changes no existing domain behaviour beyond the
**intended, additive** extension of the Artifact lifecycle. No infrastructure here.

## Decision

### 1. Placement
Human Review symbols live in `omemo_content_factory.domain.human_review`: `ReviewId`,
`ReviewStatus`, `HumanReview`, `HumanReviewView`, events and errors. The module depends only on
stdlib; its references (`run_id`, `artifact_ref`) are opaque `str` (ADR-0003 §3). Created and
mutated **only via Run**.

### 2. A new actor — `Human Reviewer`
`Actor` gains `HUMAN_REVIEWER` (additive). Per `DOMAIN_MODEL.md` §2.14 the Content Director
**opens** the gate, but the **decision is the Human Reviewer's**. So: opening a review requires
`CONTENT_DIRECTOR`; submitting its decision requires `HUMAN_REVIEWER`. Existing rules (only the
Content Director drives Run/Task/Output/Artifact) are unchanged.

### 3. States — `ReviewStatus`
`PENDING, APPROVED, REJECTED, CHANGES_REQUESTED` (`DOMAIN_MODEL.md` §2.14). Terminal: all but
`PENDING`. A review is created `PENDING` and decided exactly once (immutable thereafter).

### 4. Identity & immutable input
`HumanReview` is mutable only in its `status` + recorded `decided_by`/`reason`; its identity,
owning `run_id` and `artifact_ref` (the candidate Artifact under review) are write-once
(slots + guarded `__setattr__`, mirroring Task). Exposed only as a read-only `HumanReviewView`.

### 5. Run's additive public API
- `open_human_review(artifact_id, *, by) -> ReviewId` — Content Director only; the target
  Artifact must be `CANDIDATE`; creates a `PENDING` review, emits `HumanReviewRequested`.
- `submit_review(review_id, decision, *, by, reason=None) -> None` — Human Reviewer only;
  `decision` is `APPROVED` / `REJECTED` / `CHANGES_REQUESTED`; the review must be `PENDING`
  (else `InvalidReviewTransitionError`); records `decided_by`/`reason`; emits
  `HumanReviewApproved` / `HumanReviewRejected` (no dedicated event for `CHANGES_REQUESTED` at
  this stage, cf. Task `SKIPPED`).
- read-only: `human_reviews` (sequence of `HumanReviewView`) and `human_review(review_id)`.

### 6. Artifact lifecycle extension (the publication path)
`Artifact` transitions are extended additively (`DOMAIN_MODEL.md` §2.12):
`DRAFT → CANDIDATE` (existing); `CANDIDATE → {APPROVED, REJECTED}`; `APPROVED → PUBLISHED`.
`SUPERSEDED` (versioning) stays deferred. The structural edge table lives in `artifact.py`; the
**approval gate is enforced by Run**: `transition_artifact(artifact, CANDIDATE → APPROVED)`
requires an `APPROVED` Human Review **targeting that Artifact**, else `ArtifactNotApprovedError`.
Because `PUBLISHED` is reachable only from `APPROVED`, "no Publish without Approve" holds by
construction (`DOMAIN_MODEL.md` §6). `transition_artifact` remains Content-Director-only.

### 7. Events
`HumanReviewRequested` (open), `HumanReviewApproved`, `HumanReviewRejected` are recorded in the
Run's existing single event log (union extended additively to include `HumanReviewEvent`).

### 8. Errors
Co-located in `domain.human_review`: base `HumanReviewDomainError` + `InvalidReviewTransitionError`
and `ImmutableReviewAttributeError`. The artifact-approval gate raises `ArtifactNotApprovedError`
(in `domain.artifact`). Authorisation reuses Run's `UnauthorizedActorError`. The shared
`DomainError` base stays a rule-of-three follow-up (ADR-0005 §9).

### 9. Time
No timestamps in the asserted surface (ADR-0003 §10). `decided_by` (the author) is recorded; an
audit timestamp is deferred to an injectable clock — `DOMAIN_MODEL.md` §6's "author + timestamp"
is satisfied for author now; timestamp later.

## Deferred
- `CHANGES_REQUESTED` rework routing and `SUPERSEDED` (versioning); audit timestamp (clock);
  the QA context (flags/versions) shown to the reviewer (needs Evaluation/QA); shared
  `DomainError`/`DomainEvent` base.

## Consequences
**Positive:** the human-in-the-loop invariant becomes real and enforced; an Artifact can now
legitimately reach `PUBLISHED` only after `Approve`, enabling approval-gated delivery; the
root↔child contract extends again; everything stays through the root, immutable input, no infra.
**Negative / Trade-offs:** the Artifact lifecycle and its tests change (intended extension); Run's
public API and the `Actor` enum grow (additively); cross-entity gate (artifact ↔ review) adds a
guarded check in Run.

## Alternatives considered
- **Approve directly inside `submit_review` flips the Artifact to PUBLISHED** — rejected:
  conflates the human's decision with the Content Director's routing; the orchestrator routes.
- **Enforce the gate inside `Artifact.apply_transition`** — rejected: the Artifact entity must
  not know about reviews; the cross-entity rule belongs to the root.
- **Human Review as its own Aggregate Root** — rejected: contradicts `DOMAIN_MODEL.md` §9.1.

## References
- `DOMAIN_MODEL.md`: §2.12 (Artifact), §2.14 (Human Review), §6, §9.1, §10
- `PROJECT.md`: §1, §12 (Human Approval invariant), §4.11, §17, §18
- `ADR-0003`/`0004`/`0005`/`0006` (templates this mirrors)
