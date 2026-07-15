from __future__ import annotations

import random
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from ..models import SimulationState


class RuntimeSimulationState:
    """Own volatile central simulation state inside the dedicated worker."""

    def __init__(
        self,
        *,
        random_seed: int,
        speed: float = 1.0,
        anomaly_rate: float = 0.12,
    ) -> None:
        self._lock = threading.RLock()
        self.rng = random.Random(random_seed)
        self.speed = speed
        self.anomaly_rate = anomaly_rate
        self.running = False
        self.tick = 0
        self.last_tick_at: datetime | None = None
        self.generated_orders = 0
        self.generated_events = 0

    @contextmanager
    def operation(self) -> Iterator[None]:
        """Serialize a whole simulation step with manual control requests."""
        with self._lock:
            yield

    def snapshot(self) -> SimulationState:
        with self._lock:
            return SimulationState(
                running=self.running,
                tick=self.tick,
                speed=self.speed,
                anomaly_rate=self.anomaly_rate,
                last_tick_at=self.last_tick_at,
                generated_orders=self.generated_orders,
                generated_events=self.generated_events,
            )

    def configure(
        self,
        *,
        running: bool | None = None,
        speed: float | None = None,
        anomaly_rate: float | None = None,
    ) -> SimulationState:
        if speed is not None and speed <= 0:
            raise ValueError("simulation speed must be positive")
        if anomaly_rate is not None and not 0 <= anomaly_rate <= 1:
            raise ValueError("simulation anomaly_rate must be between 0 and 1")
        with self._lock:
            if running is not None:
                self.running = running
            if speed is not None:
                self.speed = speed
            if anomaly_rate is not None:
                self.anomaly_rate = anomaly_rate
            return self.snapshot()

    def reset_progress(self) -> None:
        """Reset volatile progress without changing operator configuration."""
        with self._lock:
            self.running = False
            self.tick = 0
            self.last_tick_at = None
            self.generated_orders = 0
            self.generated_events = 0

    def begin_step(self, occurred_at: datetime) -> int:
        with self._lock:
            self.tick += 1
            self.last_tick_at = occurred_at
            return self.tick

    def record_generated_order(self) -> None:
        with self._lock:
            self.generated_orders += 1

    def record_generated_event(self) -> None:
        with self._lock:
            self.generated_events += 1
