"""Network interface throughput measured from operating-system byte counters."""

from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class NetworkRateMetrics:
    download_bytes_per_sec: float | None
    upload_bytes_per_sec: float | None
    available: bool = True
    reason: str | None = None


class NetworkRateCollector:
    """Calculate aggregate receive/send rates between successive snapshots."""

    def __init__(self) -> None:
        self._previous: tuple[float, int, int] | None = None

    def collect(self) -> NetworkRateMetrics:
        try:
            counters = psutil.net_io_counters()
            if counters is None:
                return NetworkRateMetrics(None, None, False, "Network counters are unavailable.")
            now = time.monotonic()
            previous = self._previous
            self._previous = (now, counters.bytes_recv, counters.bytes_sent)
            if previous is None:
                return NetworkRateMetrics(None, None)

            elapsed = now - previous[0]
            if elapsed <= 0:
                return NetworkRateMetrics(None, None, False, "Waiting for the next network sample.")

            received = max(0, counters.bytes_recv - previous[1])
            sent = max(0, counters.bytes_sent - previous[2])
            return NetworkRateMetrics(received / elapsed, sent / elapsed)
        except Exception as exc:
            return NetworkRateMetrics(None, None, False, f"Network counters unavailable: {exc}")
