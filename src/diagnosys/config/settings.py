"""Runtime configuration for Diagnosys.

Values can be supplied through environment variables without a separate
configuration file.
"""

from dataclasses import asdict, dataclass, fields, replace
import json
import ipaddress
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

from platformdirs import user_data_dir


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Settings:
    """Application settings with safe, deterministic defaults."""

    data_dir: Path
    refresh_seconds: int = 2
    process_history_seconds: int = 10
    retention_days: int = 7
    network_timeout_seconds: float = 2.0
    ping_target: str = "1.1.1.1"
    dns_target: str = "example.com"
    dns_server: str = ""
    http_target: str = "https://connectivitycheck.gstatic.com/generate_204"
    alerts_enabled: bool = True
    keep_in_tray: bool = False
    baseline_enabled: bool = True
    baseline_deviation_pct: float = 20.0
    cpu_alert_threshold: float = 85.0
    memory_alert_threshold: float = 90.0
    disk_alert_threshold: float = 95.0

    def __post_init__(self) -> None:
        if self.refresh_seconds < 1:
            raise ValueError("refresh_seconds must be at least 1")
        if not 1 <= self.process_history_seconds <= 3600:
            raise ValueError("process_history_seconds must be between 1 and 3600")
        if self.retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        if not math.isfinite(self.network_timeout_seconds) or self.network_timeout_seconds <= 0:
            raise ValueError("network_timeout_seconds must be greater than zero")
        for name in ("ping_target", "dns_target", "http_target"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.dns_server.strip():
            try:
                ipaddress.ip_address(self.dns_server.strip())
            except ValueError as exc:
                raise ValueError("dns_server must be an IP address or blank for the system resolver") from exc
        parsed_http_target = urlsplit(self.http_target)
        if parsed_http_target.scheme not in {"http", "https"} or not parsed_http_target.hostname or parsed_http_target.username:
            raise ValueError("http_target must be an http:// or https:// URL without embedded credentials")
        if not math.isfinite(self.baseline_deviation_pct) or self.baseline_deviation_pct < 0:
            raise ValueError("baseline_deviation_pct must be zero or greater")
        for name in ("cpu_alert_threshold", "memory_alert_threshold", "disk_alert_threshold"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 < value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")

    @classmethod
    def from_env(cls) -> "Settings":
        # Keep the existing application directory so upgrades continue to use
        # previously collected history while still honoring an explicit override.
        data_dir = Path(
            os.getenv("DIAGNOSYS_DATA_DIR", user_data_dir("diagnosys", "diagnosys_team"))
        )
        defaults = cls(data_dir=data_dir)
        config_path = data_dir / "settings.json"
        try:
            stored = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                allowed = {item.name for item in fields(cls)} - {"data_dir"}
                defaults = replace(defaults, **{key: value for key, value in stored.items() if key in allowed})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            # A malformed local preferences file should not prevent app startup.
            pass

        retention = _positive_int(
            os.getenv("DIAGNOSYS_RETENTION_DAYS", str(defaults.retention_days)),
            "DIAGNOSYS_RETENTION_DAYS",
        )
        refresh = _positive_int(
            os.getenv("DIAGNOSYS_REFRESH_SECONDS", str(defaults.refresh_seconds)),
            "DIAGNOSYS_REFRESH_SECONDS",
        )
        process_history = _positive_int(
            os.getenv("DIAGNOSYS_PROCESS_HISTORY_SECONDS", str(defaults.process_history_seconds)),
            "DIAGNOSYS_PROCESS_HISTORY_SECONDS",
        )
        try:
            timeout = float(os.getenv("DIAGNOSYS_NETWORK_TIMEOUT", str(defaults.network_timeout_seconds)))
        except ValueError as exc:
            raise ValueError("DIAGNOSYS_NETWORK_TIMEOUT must be a number") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("DIAGNOSYS_NETWORK_TIMEOUT must be greater than zero")
        return replace(
            defaults, data_dir=data_dir, refresh_seconds=refresh,
            process_history_seconds=process_history,
            retention_days=retention, network_timeout_seconds=timeout,
        )

    def save(self) -> None:
        """Persist non-secret preferences in the local application data folder."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        values = asdict(self)
        values.pop("data_dir", None)
        destination = self.data_dir / "settings.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
        temporary.replace(destination)
