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


def _finite_number(value: object) -> float | None:
    """Return a finite sensor value without rejecting valid sub-zero temperatures."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _finite_nonnegative(value: object) -> float | None:
    """Return a non-negative physical value such as fan RPM."""
    parsed = _finite_number(value)
    return parsed if parsed is not None and parsed >= 0 else None


class ThermalCollector:
    """Collect each available sensor independently so one bad sensor cannot hide others."""

    def collect(self) -> ThermalSnapshot:
        temperature_api = getattr(psutil, "sensors_temperatures", None)
        temperature_reason = None
        raw_temperatures = {}
        if callable(temperature_api):
            try:
                raw_temperatures = temperature_api(fahrenheit=False) or {}
            except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
                temperature_reason = f"Temperature telemetry unavailable: {exc}"
        else:
            temperature_reason = "Temperature sensors are not exposed by this operating system."

        if not isinstance(raw_temperatures, dict):
            temperature_reason = "The operating system returned malformed temperature sensor data."
            raw_temperatures = {}

        temperatures: list[ThermalReading] = []
        invalid_readings = 0
        for sensor, readings in raw_temperatures.items():
            try:
                iterator = iter(readings)
            except TypeError:
                continue
            for reading in iterator:
                try:
                    current = _finite_number(getattr(reading, "current", None))
                    high = _finite_number(getattr(reading, "high", None))
                    critical = _finite_number(getattr(reading, "critical", None))
                    label = getattr(reading, "label", None) or sensor
                except Exception:
                    invalid_readings += 1
                    continue
                if current is None and high is None and critical is None:
                    invalid_readings += 1
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
            if not isinstance(raw_fans, dict):
                fan_reason = "The operating system returned malformed fan sensor data."
                raw_fans = {}
            for sensor, readings in raw_fans.items():
                try:
                    iterator = iter(readings)
                except TypeError:
                    continue
                for reading in iterator:
                    try:
                        speed = _finite_nonnegative(getattr(reading, "current", None))
                        label = getattr(reading, "label", None) or sensor
                    except Exception:
                        continue
                    if speed is not None:
                        fans.append(FanReading(str(sensor), str(label), speed))

        issues = []
        if temperature_reason:
            issues.append(temperature_reason)
        if invalid_readings:
            issues.append(f"{invalid_readings} malformed or empty temperature reading(s) were skipped")
        if fan_reason:
            issues.append(fan_reason)
        reason = "; ".join(issues) or None
        if not temperatures and not fans:
            return ThermalSnapshot(
                False,
                reason=reason or "No valid temperature or fan readings were exposed by this device.",
            )
        return ThermalSnapshot(True, tuple(temperatures), tuple(fans), reason)
