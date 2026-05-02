"""Pluggable decay policy definitions and registry."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import ClassVar


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class DecayPolicy(ABC):
    name: ClassVar[str]

    @abstractmethod
    def compute(self, current_score: float, age_days: float) -> float: ...

    @abstractmethod
    def time_to_archive(self, current_score: float, archive_threshold: float) -> float | None: ...


class ExponentialDecayPolicy(DecayPolicy):
    name = "exponential"

    def __init__(self, half_life_days: float = 30.0) -> None:
        self.half_life_days = half_life_days

    def compute(self, current_score: float, age_days: float) -> float:
        decay_lambda = math.log(2.0) / self.half_life_days
        return _clamp(current_score * math.exp(-decay_lambda * age_days), 0.0, 1.0)

    def time_to_archive(self, current_score: float, archive_threshold: float) -> float | None:
        if current_score <= 0 or archive_threshold <= 0 or archive_threshold >= current_score:
            return None
        decay_lambda = math.log(2.0) / self.half_life_days
        return -math.log(archive_threshold / current_score) / decay_lambda


class LinearDecayPolicy(DecayPolicy):
    name = "linear"

    def __init__(self, decay_rate_per_day: float | None = None, half_life_days: float | None = None) -> None:
        if half_life_days is not None:
            self.decay_rate_per_day = 1.0 / (2.0 * half_life_days)
        else:
            self.decay_rate_per_day = decay_rate_per_day if decay_rate_per_day is not None else 0.01

    def compute(self, current_score: float, age_days: float) -> float:
        return max(0.0, current_score - self.decay_rate_per_day * age_days)

    def time_to_archive(self, current_score: float, archive_threshold: float) -> float | None:
        if self.decay_rate_per_day <= 0:
            return None
        if current_score <= archive_threshold:
            return 0.0
        return (current_score - archive_threshold) / self.decay_rate_per_day


class StepDecayPolicy(DecayPolicy):
    name = "step"

    def __init__(self, steps: list[tuple[float, float]] | None = None, half_life_days: float | None = None) -> None:
        if half_life_days is not None:
            self._half_life_days = half_life_days
            self._steps_mode = "half_life"
        else:
            self._half_life_days = None
            self._steps_mode = "explicit"
            self.steps = sorted(steps or [(7, 0.9), (30, 0.6), (90, 0.3), (365, 0.05)], key=lambda s: s[0])

    def compute(self, current_score: float, age_days: float) -> float:
        if self._steps_mode == "half_life":
            periods = int(age_days // self._half_life_days)  # type: ignore[operator]
            return _clamp(current_score * (0.5**periods), 0.0, 1.0)
        multiplier = 1.0
        for threshold, step_multiplier in self.steps:
            if age_days >= threshold:
                multiplier = step_multiplier
                break
        return _clamp(current_score * multiplier, 0.0, 1.0)

    def time_to_archive(self, current_score: float, archive_threshold: float) -> float | None:
        if current_score <= archive_threshold:
            return 0.0
        if self._steps_mode == "half_life":
            import math

            if archive_threshold <= 0:
                return None
            periods = math.ceil(math.log(archive_threshold / current_score) / math.log(0.5))
            return periods * self._half_life_days  # type: ignore[operator]
        for threshold, step_multiplier in self.steps:
            if current_score * step_multiplier <= archive_threshold:
                return threshold
        return None


class DecayPolicyRegistry:
    _registry: ClassVar[dict[str, type[DecayPolicy]]] = {
        ExponentialDecayPolicy.name: ExponentialDecayPolicy,
        LinearDecayPolicy.name: LinearDecayPolicy,
        StepDecayPolicy.name: StepDecayPolicy,
    }

    @classmethod
    def get(cls, name: str) -> DecayPolicy:
        policy_cls = cls._registry.get(name)
        if policy_cls is None:
            raise ValueError(f"Unknown decay policy: {name}")
        return policy_cls()

    @classmethod
    def register(cls, policy_class: type[DecayPolicy]) -> None:
        cls._registry[policy_class.name] = policy_class
