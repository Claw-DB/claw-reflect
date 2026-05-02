"""DecayEngine — applies the configured decay policy to memory record composite scores."""

from __future__ import annotations

from claw_reflect.decay.policy import DecayPolicy, ExponentialDecayPolicy, LinearDecayPolicy, StepDecayPolicy
from claw_reflect.models.memory import MemoryRecord


class DecayEngine:
    """Applies a :class:`DecayPolicy` to a memory record and updates its composite score."""

    def __init__(self, policy: DecayPolicy | None = None) -> None:
        self._policy = policy or ExponentialDecayPolicy()

    def apply(self, record: MemoryRecord, elapsed_days: float) -> float:
        """Compute decayed score for *record* given *elapsed_days* since last refresh."""
        return self._policy.compute(record.composite_score, elapsed_days)
