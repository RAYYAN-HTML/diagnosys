"""Read-only SMART/NVMe health queries through smartctl, when installed."""
from __future__ import annotations
from dataclasses import dataclass
import json
import shutil
import subprocess

@dataclass(frozen=True)
class DiskHealth:
    device: str
    available: bool
    health_status: str = "UNKNOWN"
    temperature_c: float | None = None
    power_on_hours: int | None = None
    percentage_used: float | None = None
    reason: str | None = None

class DiskHealthCollector:
    def __init__(self, executable: str | None = None, timeout_seconds: float = 8.0):
        self.executable = executable or shutil.which("smartctl")
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 30.0))

    def collect(self, device: str) -> DiskHealth:
        if not self.executable:
            return DiskHealth(device, False, reason="smartctl is not installed. Install smartmontools to query drive health.")
        if not device or not device.strip():
            return DiskHealth(device, False, reason="A device path is required for a SMART query.")
        try:
            result = subprocess.run([self.executable, "-a", "-j", "--", device],
                capture_output=True, text=True, timeout=self.timeout_seconds,
                check=False, errors="replace")
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
            if not isinstance(payload, dict) or not payload:
                return DiskHealth(device, False, reason=result.stderr.strip() or "The drive did not return SMART JSON data.")
            smart = payload.get("smart_status", {})
            passed = smart.get("passed") if isinstance(smart, dict) else None
            status = "PASSED" if passed is True else "FAILED" if passed is False else "UNKNOWN"
            temperature = payload.get("temperature", {})
            nvme = payload.get("nvme_smart_health_information_log", {})
            power = payload.get("power_on_time", {})
            return DiskHealth(device, True, status,
                _number(temperature.get("current")) if isinstance(temperature, dict) else None,
                _integer(power.get("hours")) if isinstance(power, dict) else None,
                _number(nvme.get("percentage_used")) if isinstance(nvme, dict) else None,
                None if status != "UNKNOWN" else "SMART data returned without an overall pass/fail result.")
        except subprocess.TimeoutExpired:
            return DiskHealth(device, False, reason=f"SMART query exceeded {self.timeout_seconds:.0f} seconds.")
        except (OSError, json.JSONDecodeError) as exc:
            return DiskHealth(device, False, reason=f"SMART query failed: {exc}")

def _number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def _integer(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
