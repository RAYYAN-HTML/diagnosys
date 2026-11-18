"""Read-only thermal and fan telemetry, where the OS exposes it."""
from __future__ import annotations

import math
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class ThermalReading:
    sensor: str
    label: str
    temperature_c: float | None
    high_c: float | None = None
    critical_c: float | None = None


@dataclass(frozen=True)
class FanReading:
    sensor: str
    label: str
    speed_rpm: float | None


@dataclass(frozen=True)
class ThermalSnapshot:
    available: bool
    temperatures: tuple[ThermalReading, ...] = ()
    fans: tuple[FanReading, ...] = ()
    reason: str | None = None


def _finite_nonnegative(value: object) -> float | None:
    """Return a usable physical reading without turning invalid data into zero."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


class ThermalCollector:
    """Collect each available sensor independently so one bad sensor cannot hide others."""

    def collect(self) -> ThermalSnapshot:
        temperature_api = getattr(psutil, "sensors_temperatures", None)
        if not callable(temperature_api):
            return ThermalSnapshot(
                False,
                reason="Temperature sensors are not exposed by this operating system.",
            )

        try:
            raw_temperatures = temperature_api(fahrenheit=False) or {}
        except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
            return ThermalSnapshot(False, reason=f"Thermal telemetry unavailable: {exc}")

        temperatures: list[ThermalReading] = []
        for sensor, readings in raw_temperatures.items():
            try:
                iterator = iter(readings)
            except TypeError:
                continue
            for reading in iterator:
                current = _finite_nonnegative(getattr(reading, "current", None))
                high = _finite_nonnegative(getattr(reading, "high", None))
                critical = _finite_nonnegative(getattr(reading, "critical", None))
                label = getattr(reading, "label", None) or sensor
                if current is None and high is None and critical is None:
                    continue
                temperatures.append(
                    ThermalReading(str(sensor), str(label), current, high, critical)
                )

        fans: list[FanReading] = []
        fan_api = getattr(psutil, "sensors_fans", None)
        fan_reason = None
        if callable(fan_api):
            try:
                raw_fans = fan_api() or {}
            except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
                raw_fans = {}
                fan_reason = f"Fan telemetry unavailable: {exc}"
            for sensor, readings in raw_fans.items():
                try:
                    iterator = iter(readings)
                except TypeError:
                    continue
                for reading in iterator:
                    speed = _finite_nonnegative(getattr(reading, "current", None))
                    label = getattr(reading, "label", None) or sensor
                    if speed is not None:
                        fans.append(FanReading(str(sensor), str(label), speed))

        if not temperatures and not fans:
            reason = fan_reason or "No valid temperature or fan readings were exposed by this device."
            return ThermalSnapshot(False, reason=reason)
        return ThermalSnapshot(True, tuple(temperatures), tuple(fans), fan_reason)
