"""Read-only thermal and fan telemetry, where the OS exposes it."""
from __future__ import annotations
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

class ThermalCollector:
    def collect(self) -> ThermalSnapshot:
        api = getattr(psutil, "sensors_temperatures", None)
        if not callable(api):
            return ThermalSnapshot(False, reason="Temperature sensors are not exposed by this operating system.")
        try:
            raw = api(fahrenheit=False) or {}
            temperatures = tuple(
                ThermalReading(str(sensor), str(reading.label or sensor),
                    float(reading.current) if reading.current is not None else None,
                    float(reading.high) if reading.high is not None else None,
                    float(reading.critical) if reading.critical is not None else None)
                for sensor, readings in raw.items() for reading in readings
            )
            fan_api = getattr(psutil, "sensors_fans", None)
            fan_data = fan_api() if callable(fan_api) else {}
            fans = tuple(
                FanReading(str(sensor), str(reading.label or sensor),
                    float(reading.current) if reading.current is not None else None)
                for sensor, readings in (fan_data or {}).items() for reading in readings
            )
            if not temperatures and not fans:
                return ThermalSnapshot(False, reason="No temperature or fan readings were exposed by this device.")
            return ThermalSnapshot(True, temperatures, fans)
        except (OSError, RuntimeError, NotImplementedError, AttributeError, TypeError, ValueError, psutil.Error) as exc:
            return ThermalSnapshot(False, reason=f"Thermal telemetry unavailable: {exc}")
