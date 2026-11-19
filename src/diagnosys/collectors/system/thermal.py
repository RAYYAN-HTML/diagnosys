"""Read-only thermal and fan telemetry, where the OS exposes it."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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


def _mapping_items(value: object) -> tuple[list[tuple[Any, Any]], bool]:
    """Read sensor groups defensively because third-party drivers may return broken mappings."""
    if not isinstance(value, Mapping):
        return [], True
    try:
        return list(value.items()), False
    except Exception:
        return [], True


def _readings(value: object) -> tuple[list[object], bool]:
    """Materialize one sensor's readings without letting a broken iterator abort collection."""
    try:
        iterator = iter(value)
    except Exception:
        return [], True

    result: list[object] = []
    while True:
        try:
            result.append(next(iterator))
        except StopIteration:
            return result, False
        except Exception:
            return result, True


class ThermalCollector:
    """Collect each available sensor independently so one bad sensor cannot hide others."""

    def collect(self) -> ThermalSnapshot:
        temperature_api = getattr(psutil, "sensors_temperatures", None)
        temperature_reason = None
        raw_temperatures: object = {}
        if callable(temperature_api):
            try:
                raw_temperatures = temperature_api(fahrenheit=False) or {}
            except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
                temperature_reason = f"Temperature telemetry unavailable: {exc}"
        else:
            temperature_reason = "Temperature sensors are not exposed by this operating system."

        temperature_groups, malformed_temperature_groups = _mapping_items(raw_temperatures)
        if malformed_temperature_groups:
            temperature_reason = "The operating system returned malformed temperature sensor data."

        temperatures: list[ThermalReading] = []
        invalid_readings = 0
        for sensor, raw_readings in temperature_groups:
            readings, iteration_failed = _readings(raw_readings)
            if iteration_failed:
                invalid_readings += 1
            for reading in readings:
                try:
                    current = _finite_number(getattr(reading, "current", None))
                    high = _finite_number(getattr(reading, "high", None))
                    critical = _finite_number(getattr(reading, "critical", None))
                    label = getattr(reading, "label", None) or sensor
                    sensor_name = str(sensor)
                    label_name = str(label)
                except Exception:
                    invalid_readings += 1
                    continue
                if current is None and high is None and critical is None:
                    invalid_readings += 1
                    continue
                temperatures.append(
                    ThermalReading(sensor_name, label_name, current, high, critical)
                )

        fans: list[FanReading] = []
        fan_api = getattr(psutil, "sensors_fans", None)
        fan_reason = None
        if callable(fan_api):
            try:
                raw_fans: object = fan_api() or {}
            except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
                raw_fans = {}
                fan_reason = f"Fan telemetry unavailable: {exc}"

            fan_groups, malformed_fan_groups = _mapping_items(raw_fans)
            if malformed_fan_groups:
                fan_reason = "The operating system returned malformed fan sensor data."
            invalid_fans = 0
            for sensor, raw_readings in fan_groups:
                readings, iteration_failed = _readings(raw_readings)
                if iteration_failed:
                    invalid_fans += 1
                for reading in readings:
                    try:
                        speed = _finite_nonnegative(getattr(reading, "current", None))
                        label = getattr(reading, "label", None) or sensor
                        sensor_name = str(sensor)
                        label_name = str(label)
                    except Exception:
                        invalid_fans += 1
                        continue
                    if speed is None:
                        invalid_fans += 1
                        continue
                    fans.append(FanReading(sensor_name, label_name, speed))
            if invalid_fans:
                detail = f"{invalid_fans} malformed or unreadable fan reading(s) were skipped"
                fan_reason = f"{fan_reason}; {detail}" if fan_reason else detail

        issues = []
        if temperature_reason:
            issues.append(temperature_reason)
        if invalid_readings:
            issues.append(f"{invalid_readings} malformed or unreadable temperature reading(s) were skipped")
        if fan_reason:
            issues.append(fan_reason)
        reason = "; ".join(issues) or None
        if not temperatures and not fans:
            return ThermalSnapshot(
                False,
                reason=reason or "No valid temperature or fan readings were exposed by this device.",
            )
        return ThermalSnapshot(True, tuple(temperatures), tuple(fans), reason)
