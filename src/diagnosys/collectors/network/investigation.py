"""Read-only local network path and Wi-Fi diagnostics."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess


class NetworkInvestigator:
    def collect(self, target: str, timeout_seconds: float = 2.0) -> dict:
        """Collect a default gateway, bounded route trace, and Wi-Fi summary."""
        gateway = self._default_gateway()
        gateway_ping = None
        if gateway.get("available"):
            from diagnosys.collectors.network.ping import PingCollector

            gateway_ping = PingCollector(
                target=gateway["address"], count=2, timeout_sec=timeout_seconds
            ).collect()
        return {
            "target": target,
            "gateway": gateway,
            "gateway_ping": gateway_ping,
            "route": self._trace_route(target, timeout_seconds),
            "wifi": self._wifi_summary(),
        }

    @staticmethod
    def _run(command: list[str], timeout: float) -> str:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            check=False, errors="replace",
        )
        return result.stdout + result.stderr

    def _default_gateway(self) -> dict:
        system = platform.system().lower()
        try:
            if system == "windows":
                output = self._run(["route", "print", "-4"], 3)
                for line in output.splitlines():
                    match = re.match(r"\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d{1,3}(?:\.\d{1,3}){3})\s+", line)
                    if match:
                        return {"available": True, "address": match.group(1)}
            elif system == "darwin" and shutil.which("route"):
                output = self._run(["route", "-n", "get", "default"], 3)
                match = re.search(r"^\s*gateway:\s*(\S+)", output, re.MULTILINE)
                if match:
                    return {"available": True, "address": match.group(1)}
            elif shutil.which("ip"):
                output = self._run(["ip", "route", "show", "default"], 3)
                match = re.search(r"\bdefault\s+via\s+(\S+)", output)
                if match:
                    return {"available": True, "address": match.group(1)}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": False, "reason": str(exc)}
        return {"available": False, "reason": "Default gateway could not be discovered on this platform."}

    def _trace_route(self, target: str, timeout_seconds: float) -> dict:
        system = platform.system().lower()
        try:
            if system == "windows":
                command = ["tracert", "-d", "-h", "8", "-w", str(max(250, int(timeout_seconds * 500))), target]
            else:
                executable = shutil.which("traceroute") or shutil.which("tracepath")
                if not executable:
                    return {"available": False, "reason": "traceroute or tracepath is not installed."}
                if executable.endswith("tracepath"):
                    command = [executable, "-m", "8", "-n", target]
                else:
                    command = [executable, "-n", "-m", "8", "-q", "1", "-w", "1", target]
            output = self._run(command, timeout=15)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            return {"available": bool(lines), "lines": lines[-12:], "reason": None if lines else "No route data was returned."}
        except FileNotFoundError:
            return {"available": False, "reason": "Route tracing is unavailable on this system."}
        except subprocess.TimeoutExpired:
            return {"available": False, "reason": "Route tracing exceeded its 15 second limit."}
        except OSError as exc:
            return {"available": False, "reason": str(exc)}

    def _wifi_summary(self) -> dict:
        if platform.system().lower() != "windows":
            return {"available": False, "reason": "Wi-Fi signal details are currently available on Windows only."}
        try:
            output = self._run(["netsh", "wlan", "show", "interfaces"], 4)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": False, "reason": str(exc)}
        values = {}
        for key in ("SSID", "Signal", "Channel", "Radio type"):
            match = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", output, re.MULTILINE | re.IGNORECASE)
            if match:
                values[key.lower().replace(" ", "_")] = match.group(1).strip()
        if not values:
            return {"available": False, "reason": "No active Wi-Fi connection was reported."}
        values["available"] = True
        return values
