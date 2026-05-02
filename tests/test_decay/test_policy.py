"""Tests for decay policy implementations."""

from __future__ import annotations

import pytest

from claw_reflect.decay.policy import ExponentialDecayPolicy, LinearDecayPolicy, StepDecayPolicy


class TestExponentialDecayPolicy:
    def test_no_decay_at_zero_days(self) -> None:
        policy = ExponentialDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 0.0) == pytest.approx(1.0)

    def test_halves_at_half_life(self) -> None:
        policy = ExponentialDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 30.0) == pytest.approx(0.5, rel=1e-6)

    def test_decay_reduces_score(self) -> None:
        policy = ExponentialDecayPolicy(half_life_days=30.0)
        assert policy.compute(0.8, 10.0) < 0.8


class TestLinearDecayPolicy:
    def test_no_decay_at_zero_days(self) -> None:
        policy = LinearDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 0.0) == pytest.approx(1.0)

    def test_reaches_zero_at_double_half_life(self) -> None:
        policy = LinearDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 60.0) == pytest.approx(0.0)

    def test_clamped_at_zero(self) -> None:
        policy = LinearDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 999.0) == 0.0


class TestStepDecayPolicy:
    def test_no_decay_within_half_life(self) -> None:
        policy = StepDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 29.9) == pytest.approx(1.0)

    def test_halves_at_one_step(self) -> None:
        policy = StepDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 30.0) == pytest.approx(0.5)

    def test_quarters_at_two_steps(self) -> None:
        policy = StepDecayPolicy(half_life_days=30.0)
        assert policy.compute(1.0, 60.0) == pytest.approx(0.25)
