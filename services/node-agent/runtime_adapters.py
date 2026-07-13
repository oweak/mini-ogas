from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

StateBuilder = Callable[..., dict]


class RuntimeAdapter(ABC):
    """Stable simulation/device boundary consumed by heartbeat generation."""

    name = "runtime"

    @abstractmethod
    def build_state(self, profile: Any, tick: int, scenario_id: str) -> dict:
        raise NotImplementedError


class SimpleRuntimeAdapter(RuntimeAdapter):
    name = "simple"

    def __init__(self, state_builder: StateBuilder) -> None:
        self._state_builder = state_builder

    def build_state(self, profile: Any, tick: int, scenario_id: str) -> dict:
        return self._state_builder(profile, tick)


class SimPyRuntimeAdapter(RuntimeAdapter):
    name = "simpy"

    def __init__(self, state_builder: StateBuilder, random_seed: int) -> None:
        self._state_builder = state_builder
        self._random_seed = random_seed

    def build_state(self, profile: Any, tick: int, scenario_id: str) -> dict:
        return self._state_builder(
            profile,
            tick,
            random_seed=self._random_seed,
            scenario_id=scenario_id,
        )
