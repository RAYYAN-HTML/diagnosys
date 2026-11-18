"""Read-only SMART/NVMe discovery and health queries through smartctl."""
from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import subprocess
from typing import Any


@dataclass(frozen=True)
class DiskDevice:
    device: str
    protocol: str | None = None
    name: str | None = None
    device_type: str | None = None


@dataclass(frozen=True)
class DiskDiscovery:
    available: bool
    devices: tuple[DiskDevice, ...] = ()
    reason: str | None = None
    state: str = "unknown"


@dataclass(frozen=True)
class DiskHealth:
    device: str
    available: bool
    health_status: str = "UNKNOWN"
    temperature_c: float | None = None
    power_on_hours: int | None = None
    percentage_used: float | None = None
    reason: str | None = None
    state: str = "unknown"
    media_errors: int | None = None
    critical_warning: int | None = None
    available_spare_percent: float | None = None
    spare_threshold_percent: float | None = None
    reallocated_sectors: int | None = None


class DiskHealthCollector:
    """Discover supported drives and query health with read-only smartctl calls."""

    def __init__(self, executable: str | None = None, timeout_seconds: float = 8.0):
        self.executable = executable or shutil.which("smartctl")
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 30.0))

    def discover(self) -> DiskDiscovery:
        if not self.executable:
            return DiskDiscovery(
                False,
                reason="smartctl is not installed. Install smartmontools to discover drive health.",
                state="tool_missing",
            )
        try:
            result = subprocess.run(
                [self.executable, "--scan-open", "-j"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return DiskDiscovery(
                False, reason=f"Drive discovery exceeded {self.timeout_seconds:.0f} seconds.",
                state="timeout",
            )
        except OSError as exc:
            return DiskDiscovery(False, reason=f"Could not start smartctl: {exc}", state="execution_error")

        try:
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            detail = result.stderr.strip() or "smartctl returned invalid discovery JSON."
            return DiskDiscovery(False, reason=detail, state="query_error")

        raw_devices = payload.get("devices", []) if isinstance(payload, dict) else []
        devices: list[DiskDevice] = []
        for item in raw_devices if isinstance(raw_devices, list) else []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            devices.append(DiskDevice(
                device=name,
                protocol=_text(item.get("protocol")),
                name=_text(item.get("info_name")),
                device_type=_text(item.get("type")),
            ))

        if not devices:
            detail = result.stderr.strip() or "smartctl did not discover any queryable drives. The controller or enclosure may not expose SMART data."
            failure = _failure_state(detail)
            state = failure if failure != "query_error" else "no_devices"
            return DiskDiscovery(False, reason=detail, state=state)
        return DiskDiscovery(True, tuple(devices), state="available")

    def collect(self, device: str) -> DiskHealth:
        if not self.executable:
            return DiskHealth(
                device, False,
                reason="smartctl is not installed. Install smartmontools to query drive health.",
                state="tool_missing",
            )
        if not device or not device.strip():
            return DiskHealth(device, False, reason="A device path is required for a SMART query.", state="invalid_device")
        try:
            result = subprocess.run(
                [self.executable, "-a", "-j", "--", device],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return DiskHealth(
                device, False,
                reason=f"SMART query exceeded {self.timeout_seconds:.0f} seconds.",
                state="timeout",
            )
        except OSError as exc:
            return DiskHealth(device, False, reason=f"Could not start smartctl: {exc}", state="execution_error")

        try:
            payload = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            detail = result.stderr.strip() or "The drive did not return valid SMART JSON data."
            return DiskHealth(device, False, reason=detail, state=_failure_state(detail))

        if not isinstance(payload, dict) or not payload:
            detail = result.stderr.strip() or "The drive did not return SMART JSON data."
            return DiskHealth(device, False, reason=detail, state=_failure_state(detail))

        smart = payload.get("smart_status")
        passed = smart.get("passed") if isinstance(smart, dict) else None
        nvme = payload.get("nvme_smart_health_information_log")
        nvme = nvme if isinstance(nvme, dict) else {}
        temperature = payload.get("temperature")
        temperature = temperature if isinstance(temperature, dict) else {}
        power = payload.get("power_on_time")
        power = power if isinstance(power, dict) else {}

        critical_warning = _integer(nvme.get("critical_warning"))
        if passed is False or (critical_warning is not None and critical_warning != 0):
            health_status, state = "FAILED", "warning"
        elif passed is True or (passed is None and bool(nvme) and critical_warning == 0):
            health_status, state = "PASSED", "healthy"
        else:
            health_status, state = "UNKNOWN", "unknown"

        attributes = payload.get("ata_smart_attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        table = attributes.get("table")
        table = table if isinstance(table, list) else []
        reallocated = _attribute_raw(table, {"reallocated_sector_ct", "reallocated_sector_count"}, {5})
        ata_temperature = _attribute_raw(table, {"temperature_celsius", "airflow_temperature_cel"}, {194, 190})
        ata_power = _attribute_raw(table, {"power_on_hours"}, {9})
        media_errors = _integer(nvme.get("media_errors"))
        if state == "healthy" and (
            (media_errors is not None and media_errors > 0)
            or (reallocated is not None and reallocated > 0)
        ):
            health_status, state = "WARNING", "warning"

        temperature_value = _number(temperature.get("current"))
        if temperature_value is None:
            temperature_value = ata_temperature
        power_hours = _integer(power.get("hours"))
        if power_hours is None:
            power_hours = _integer(ata_power)

        reason = None
        if state == "unknown":
            reason = "SMART data was returned without a conclusive overall health result."
        elif state == "warning":
            if passed is False or (critical_warning is not None and critical_warning != 0):
                reason = "The drive reported a failed SMART status or an NVMe critical warning. Review the raw health attributes and back up important data."
            else:
                indicators = []
                if media_errors is not None and media_errors > 0:
                    indicators.append(f"{media_errors} NVMe media error(s)")
                if reallocated is not None and reallocated > 0:
                    indicators.append(f"{int(reallocated)} reallocated sector(s)")
                reason = "The drive reports " + " and ".join(indicators) + ". Review the device-specific health details and back up important data."

        return DiskHealth(
            device=device,
            available=True,
            health_status=health_status,
            temperature_c=temperature_value,
            power_on_hours=power_hours,
            percentage_used=_number(nvme.get("percentage_used")),
            reason=reason,
            state=state,
            media_errors=media_errors,
            critical_warning=critical_warning,
            available_spare_percent=_number(nvme.get("available_spare")),
            spare_threshold_percent=_number(nvme.get("available_spare_threshold")),
            reallocated_sectors=_integer(reallocated),
        )


def _attribute_raw(table: list[Any], names: set[str], ids: set[int]) -> float | None:
    for item in table:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").casefold()
        attribute_id = _integer(item.get("id"))
        if name in names or attribute_id in ids:
            raw = item.get("raw", {})
            if isinstance(raw, dict):
                value = raw.get("value")
                if value is None:
                    value = raw.get("string")
                parsed = _number(value)
                if parsed is not None:
                    return parsed
    return None


def _failure_state(detail: str) -> str:
    lowered = detail.casefold()
    if any(word in lowered for word in ("permission denied", "operation not permitted", "access denied")):
        return "permission_denied"
    if any(word in lowered for word in ("unsupported", "unknown usb", "no such device")):
        return "unsupported"
    return "query_error"


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
