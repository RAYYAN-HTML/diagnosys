"""Platform capability discovery.

Discovery is deliberately lightweight: it checks APIs and local permissions,
but does not run network probes or make changes to the machine.
"""

import platform
import shutil
import shutil
from typing import Any

import psutil

from diagnosys.models.capabilities import Capability


def _check(name: str, available: bool, reason: str | None = None) -> Capability:
    return Capability(name=name, available=available, reason=None if available else reason)


def discover_capabilities() -> list[Capability]:
    """Return the capabilities exposed by the current runtime and OS."""
    return [
        _check("cpu", hasattr(psutil, "cpu_percent"), "psutil CPU API unavailable"),
        _check("memory", hasattr(psutil, "virtual_memory"), "psutil memory API unavailable"),
        _check("disk", hasattr(psutil, "disk_usage"), "psutil disk API unavailable"),
        _check("processes", hasattr(psutil, "process_iter"), "process API unavailable"),
        _check("network_interfaces", hasattr(psutil, "net_if_stats"), "network interface API unavailable"),
        _check("battery", hasattr(psutil, "sensors_battery"), "battery API unavailable on this platform"),
        _check("temperatures", hasattr(psutil, "sensors_temperatures"), "temperature API unavailable on this platform"),
        _check("load_average", hasattr(psutil, "getloadavg"), "load average API unavailable on this platform"),
        _check(
            "windows_event_log",
            platform.system().lower() == "windows" and bool(shutil.which("powershell") or shutil.which("pwsh")),
            "Windows event log correlation requires Windows and PowerShell",
        ),
        _check(
            "route_tracing",
            platform.system().lower() == "windows" or bool(shutil.which("traceroute") or shutil.which("tracepath")),
            "tracert, traceroute, or tracepath is unavailable",
        ),
        _check(
            "windows_event_log",
            platform.system().lower() == "windows" and bool(shutil.which("powershell") or shutil.which("pwsh")),
            "Windows event log correlation requires Windows and PowerShell",
        ),
        _check(
            "route_tracing",
            platform.system().lower() == "windows" or bool(shutil.which("traceroute") or shutil.which("tracepath")),
            "tracert, traceroute, or tracepath is unavailable",
        ),
    ]


def runtime_info() -> dict[str, Any]:
    """Return stable runtime metadata for reports and the future GUI."""
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "psutil_version": getattr(psutil, "__version__", "unknown"),
        "capabilities": [cap.to_dict() for cap in discover_capabilities()],
    }
