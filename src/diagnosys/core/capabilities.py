"""Lightweight platform capability discovery."""
from __future__ import annotations
import platform
import shutil
from typing import Any
import psutil
from diagnosys.models.capabilities import Capability

def _check(name: str, available: bool, reason: str | None = None) -> Capability:
    return Capability(name=name, available=available, reason=None if available else reason)

def discover_capabilities() -> list[Capability]:
    system = platform.system().lower()
    return [
        _check("cpu", hasattr(psutil, "cpu_percent"), "psutil CPU API unavailable"),
        _check("memory", hasattr(psutil, "virtual_memory"), "psutil memory API unavailable"),
        _check("disk", hasattr(psutil, "disk_usage"), "psutil disk API unavailable"),
        _check("processes", hasattr(psutil, "process_iter"), "process API unavailable"),
        _check("network_interfaces", hasattr(psutil, "net_if_stats"), "network interface API unavailable"),
        _check("battery", callable(getattr(psutil, "sensors_battery", None)), "Battery telemetry is not exposed on this platform."),
        _check("thermal_sensors", callable(getattr(psutil, "sensors_temperatures", None)), "Temperature sensors are not exposed on this platform."),
        _check("smart_disk_health", bool(shutil.which("smartctl")), "Install smartmontools to query supported drive health."),
        _check("game_process_monitoring", hasattr(psutil, "process_iter"), "Process inspection is unavailable."),
        _check("windows_event_log", system == "windows" and bool(shutil.which("powershell") or shutil.which("pwsh")), "Windows event log correlation requires Windows and PowerShell."),
        _check("route_tracing", system == "windows" or bool(shutil.which("traceroute") or shutil.which("tracepath")), "tracert, traceroute, or tracepath is unavailable."),
    ]

def runtime_info() -> dict[str, Any]:
    return {
        "os": platform.system(), "os_release": platform.release(),
        "architecture": platform.machine(), "python_version": platform.python_version(),
        "psutil_version": getattr(psutil, "__version__", "unknown"),
        "capabilities": [cap.to_dict() for cap in discover_capabilities()],
    }
