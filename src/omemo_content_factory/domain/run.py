"""Run domain model — first working implementation of the aggregate.

This module implements the ``Run`` aggregate exactly as agreed in **ADR-0003 "Run domain
model interface contract"**, the sole source of the technical contract. The public interface
(the ``create`` factory, the read-only properties, ``transition`` and the
``RunStatus`` / ``Actor`` / ``ReworkPolicy`` / event / error types) is unchanged from the
accepted contract — only ``Run`` itself moves from a ``Protocol`` stub to a concrete,
instantiable aggregate, as ADR-0003 §3 requires (construction via ``Run.create()``).

It contains no infrastructure, persistence, serialization, async/threading, child aggregates
or integrations (out of scope; see the module's accompanying acceptance docs).

Scenario identifiers in docstrings (e.g. ``HP-01``, ``FL-03``) refer to `RUN_ACCEPTANCE.md`.

Representation note (per ADR-0003 §3): identifiers and references the domain leaves opaque are
represented as plain ``str`` references — the minimal typing needed, with no added semantics.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class RunStatus(Enum):
    """The seven lifecycle states of a Run (RUN_SPEC.md §4; ADR-0003 §2).

    ``COMPLETED`` and ``FAILED`` are the terminal states.
    """

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_QA = "waiting_qa"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class Actor(Enum):
    """Role requesting a Run state change (ADR-0003 §4).

    Represents the existing rule "only the Content Director changes status"
    (RUN_SPEC.md §5, invariant 3). ``AGENT`` is an example of a non-authorised role.
    """

    CONTENT_DIRECTOR = "content_director"
    AGENT = "agent"


@dataclass(frozen=True, slots=True)
class ReworkPolicy:
    """Value Object bounding the number of rework iterations (ADR-0003 §6).

    ``max_rework_iterations`` is a configurable policy value, not a domain rule; the default
    is ``3``. Governs scenarios ``RW-04`` / ``INV-08``.
    """

    max_rework_iterations: int = 3


# --- Domain events -----------------------------------------------------------------------
# Emitted by a Run on successful transitions (ADR-0003 §7). Verified by EV-01..EV-05.


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Base type for Run domain events. Carries the owning Run identifier."""

    run_id: str


@dataclass(frozen=True, slots=True)
class RunCreated(RunEvent):
    """Emitted when a Run is created (`EV-01`; happy path `HP-01`).

    Carries the fixed input references captured at creation (`ID-02`).
    """

    content_brief_ref: str
    workflow_version_ref: str


@dataclass(frozen=True, slots=True)
class RunQueued(RunEvent):
    """Emitted on ``CREATED -> QUEUED`` (`EV-02`)."""


@dataclass(frozen=True, slots=True)
class RunStarted(RunEvent):
    """Emitted on the first ``QUEUED -> RUNNING`` only (`EV-03`).

    Re-entry to ``RUNNING`` via rework does **not** emit this event (RUN_SPEC.md §7).
    """


@dataclass(frozen=True, slots=True)
class RunCompleted(RunEvent):
    """Emitted on reaching ``COMPLETED`` after Approve (`EV-04`; `HP-02`)."""


@dataclass(frozen=True, slots=True)
class RunFailed(RunEvent):
    """Emitted on reaching ``FAILED`` (`EV-05`; `FL-12`). Carries the failure reason."""

    reason: str | None = None


# --- Domain errors -----------------------------------------------------------------------
# Raised on domain-rule violations (ADR-0003 §8). Distinct from technical failures.


class RunDomainError(Exception):
    """Base class for all Run domain-rule violations."""


class InvalidTransitionError(RunDomainError):
    """A requested state transition is not allowed.

    Covers forbidden edges, reopening a terminal state and state skips
    (`FL-01`, `FL-03`, `FL-04`, `FL-09`, `FL-10`, `FL-11`; invariants `INV-04`, `INV-05`).
    """


class UnauthorizedActorError(RunDomainError):
    """A state change was requested by an actor other than the Content Director.

    Covers `FL-08` (invariant `INV-03`).
    """


class ImmutableAttributeError(RunDomainError):
    """An attempt was made to change an immutable attribute of a Run.

    Covers the run identifier and fixed input references
    (`FL-05`, `FL-06`, `FL-07`; invariant `INV-02`; identity `ID-01`, `ID-02`).
    """


class ReworkLimitExceededError(RunDomainError):
    """A rework re-entry would exceed the configured rework policy bound.

    Covers `RW-04` (invariant `INV-08`).
    """


class AggregateBoundaryError(RunDomainError):
    """A child was created or attached outside its owning Run, or bound to another Run.

    Covers `AGG-01`..`AGG-06` (invariant `INV-07`). Child entity types are out of scope at
    this stage (ADR-0003 §9), so this error exists in the contract ahead of those entities.
    """


# --- Run aggregate -----------------------------------------------------------------------

# Allowed state transitions (RUN_SPEC.md §4). A terminal state has no outgoing edges, so any
# transition out of it is rejected. "Any non-terminal -> FAILED" is encoded per source.
_ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.QUEUED, RunStatus.FAILED},
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.WAITING_QA, RunStatus.FAILED},
    RunStatus.WAITING_QA: {RunStatus.WAITING_HUMAN, RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.WAITING_HUMAN: {RunStatus.COMPLETED, RunStatus.RUNNING, RunStatus.FAILED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
}

# States from which a return to RUNNING counts as a rework iteration (RUN_SPEC.md §4, §7).
_REWORK_SOURCES: set[RunStatus] = {RunStatus.WAITING_QA, RunStatus.WAITING_HUMAN}

# Immutable public attributes AND their private backing fields. Neither a public name
# (``run.run_id = ...``) nor its backing field (``run._run_id = ...``) may be reassigned
# after construction, so immutability is real rather than surface-only (ADR-0003 §3, §8).
_IMMUTABLE_ATTRIBUTES = frozenset(
    {
        "run_id",
        "content_brief_ref",
        "workflow_version_ref",
        "_run_id",
        "_content_brief_ref",
        "_workflow_version_ref",
    }
)


class Run:
    """The Run aggregate root — the consistency boundary of one content production.

    Concrete implementation of the contract in ADR-0003. Construct via :meth:`create`.
    The Content Director is the only actor permitted to drive state transitions.

    ``__slots__`` (no instance ``__dict__``) together with a guarded ``__setattr__`` make
    the immutable input fields genuinely write-once: both the public names and their
    private backing fields are protected, and stray attribute injection is closed off.
    """

    __slots__ = (
        "_content_brief_ref",
        "_events",
        "_failure_reason",
        "_rework_count",
        "_rework_policy",
        "_run_id",
        "_status",
        "_workflow_version_ref",
    )

    _run_id: str
    _content_brief_ref: str
    _workflow_version_ref: str
    _rework_policy: ReworkPolicy
    _status: RunStatus
    _rework_count: int
    _failure_reason: str | None
    _events: list[RunEvent]

    def __init__(
        self,
        run_id: str,
        content_brief_ref: str,
        workflow_version_ref: str,
        rework_policy: ReworkPolicy,
    ) -> None:
        # Immutable inputs are written exactly once, here, bypassing the guard below.
        object.__setattr__(self, "_run_id", run_id)
        object.__setattr__(self, "_content_brief_ref", content_brief_ref)
        object.__setattr__(self, "_workflow_version_ref", workflow_version_ref)
        # Mutable state is assigned normally and flows through the guarded __setattr__.
        self._rework_policy = rework_policy
        self._status = RunStatus.CREATED
        self._rework_count = 0
        self._failure_reason = None
        self._events = []

    def __setattr__(self, name: str, value: object) -> None:
        """Reject reassignment of immutable attributes and their backing fields.

        Guards both the public names (``run.run_id = ...``) and the private storage
        (``run._run_id = ...``), so the protection is real, not surface-only
        (`FL-05`, `FL-06`, `FL-07`; `INV-02`).
        """
        if name in _IMMUTABLE_ATTRIBUTES:
            raise ImmutableAttributeError(f"'{name}' is immutable after creation")
        super().__setattr__(name, value)

    @classmethod
    def create(
        cls,
        run_id: str,
        content_brief_ref: str,
        workflow_version_ref: str,
        rework_policy: ReworkPolicy | None = None,
    ) -> Run:
        """Create a Run in ``CREATED`` and emit ``RunCreated``.

        ``run_id``, ``content_brief_ref`` and ``workflow_version_ref`` are explicit and become
        read-only (`ID-01`, `ID-02`; `INV-02`). ``rework_policy`` defaults to ``ReworkPolicy()``
        when ``None``. Establishes the start of the happy path (`HP-01`, `EV-01`).
        """
        run = cls(
            run_id=run_id,
            content_brief_ref=content_brief_ref,
            workflow_version_ref=workflow_version_ref,
            rework_policy=rework_policy if rework_policy is not None else ReworkPolicy(),
        )
        run._record(
            RunCreated(
                run_id=run_id,
                content_brief_ref=content_brief_ref,
                workflow_version_ref=workflow_version_ref,
            )
        )
        return run

    @property
    def run_id(self) -> str:
        """Stable, immutable identity of the Run (`ID-01`; `FL-07`)."""
        return self._run_id

    @property
    def content_brief_ref(self) -> str:
        """Fixed reference to the Content Brief; immutable after creation (`FL-05`, `ID-02`)."""
        return self._content_brief_ref

    @property
    def workflow_version_ref(self) -> str:
        """Fixed reference to the Workflow version; immutable after creation (`FL-06`)."""
        return self._workflow_version_ref

    @property
    def status(self) -> RunStatus:
        """The single current state of the Run — exactly one at any time (`INV-01`)."""
        return self._status

    @property
    def rework_count(self) -> int:
        """Number of rework iterations performed so far (`RW-04`; `INV-08`)."""
        return self._rework_count

    @property
    def failure_reason(self) -> str | None:
        """Reason captured when the Run reached ``FAILED`` (`FL-12`; `EV-05`)."""
        return self._failure_reason

    @property
    def events(self) -> Sequence[RunEvent]:
        """Ordered, read-only sequence of events emitted since creation (`EV-01`..`EV-05`)."""
        return tuple(self._events)

    def transition(self, to: RunStatus, by: Actor, reason: str | None = None) -> None:
        """Request a guarded state transition driven by ``by`` (the Content Director).

        Permits only the edges of RUN_SPEC.md §4 and emits the corresponding event (ADR-0003
        §5, §7). Drives the happy path and rework (`HP-01`, `HP-02`, `RW-01`..`RW-03`) and
        rejects domain-rule violations via the errors above (`FL-01`..`FL-12`; invariants
        `INV-01`..`INV-06`, `INV-08`; events `EV-02`..`EV-05`). ``reason`` accompanies a
        ``FAILED`` transition.
        """
        self._ensure_authorised(by)
        self._ensure_allowed(to)
        if self._is_rework(to):
            self._register_rework()
        previous = self._status
        self._status = to
        if to is RunStatus.FAILED:
            self._failure_reason = reason
        event = self._event_for(previous, to, reason)
        if event is not None:
            self._record(event)

    def _ensure_authorised(self, by: Actor) -> None:
        """Only the Content Director may change status (`FL-08`; `INV-03`)."""
        if by is not Actor.CONTENT_DIRECTOR:
            raise UnauthorizedActorError(f"{by} may not change Run status")

    def _ensure_allowed(self, to: RunStatus) -> None:
        """Reject any edge outside the allowed table, including out of a terminal (`FL-*`)."""
        if to not in _ALLOWED_TRANSITIONS[self._status]:
            raise InvalidTransitionError(f"transition {self._status} -> {to} is not allowed")

    def _is_rework(self, to: RunStatus) -> bool:
        """A return to RUNNING from a waiting state is a rework iteration (RUN_SPEC.md §4)."""
        return to is RunStatus.RUNNING and self._status in _REWORK_SOURCES

    def _register_rework(self) -> None:
        """Bound rework by the policy; reject the iteration that would exceed it (`RW-04`)."""
        if self._rework_count >= self._rework_policy.max_rework_iterations:
            raise ReworkLimitExceededError("rework limit exceeded")
        self._rework_count += 1

    def _event_for(self, previous: RunStatus, to: RunStatus, reason: str | None) -> RunEvent | None:
        """Map a successful edge to its Run event, or ``None`` when the edge emits none."""
        if to is RunStatus.QUEUED:
            return RunQueued(run_id=self._run_id)
        if to is RunStatus.RUNNING and previous is RunStatus.QUEUED:
            return RunStarted(run_id=self._run_id)
        if to is RunStatus.COMPLETED:
            return RunCompleted(run_id=self._run_id)
        if to is RunStatus.FAILED:
            return RunFailed(run_id=self._run_id, reason=reason)
        return None

    def _record(self, event: RunEvent) -> None:
        """Append an emitted event to the Run's history."""
        self._events.append(event)
