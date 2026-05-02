"""DecayPolicy implementations — exponential, linear, and step score decay functions."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from claw_reflect.config import settings


class DecayPolicy(ABC):
    """Abstract decay policy that maps (current_score, elapsed_days) → new_score."""

    @abstractmethod
    def compute(self, score: float, elapsed_days: float) -> float:
        """Return the decayed score given current *score* and *elapsed_days*."""


class ExponentialDecayPolicy(DecayPolicy):
    """Score decays exponentially with a configurable half-life."""

    def __init__(self, half_life_days: float | None = None) -> None:
        self._half_life = half_life_days or settings.decay_half_life_days

    def compute(self, score: float, elapsed_days: float) -> float:
        """Return ``score * 2^(-elapsed_days / half_life)``."""
        return score * math.pow(0.5, elapsed_days / self._half_life)


class LinearDecayPolicy(DecayPolicy):
    """Score decays linearly, reaching zero after *half_life_days * 2* days."""

    def __init__(self, half_life_days: float | None = None) -> None:
        self._half_life = half_life_days or settings.decay_half_life_days

    def compute(self, score: float, elapsed_days: float) -> float:
        """Return linearly decayed score, clamped to zero."""
        rate = score / (self._half_life * 2)
        return max(0.0, score - rate * elapsed_days)


class StepDecayPolicy(DecayPolicy):
    """Score halves at each half-life interval (discrete step function)."""

    def __init__(self, half_life_days: float | None = None) -> None:
        self._half_life = half_life_days or settings.decay_half_life_days

    def compute(self, score: float, elapsed_days: float) -> float:
        """Return score halved for each complete half-life interval elapsed."""
        steps = int(elapsed_days / self._half_life)
        return score * math.pow(0.5, steps)
