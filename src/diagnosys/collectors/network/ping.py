import subprocess
import platform
import math
import re
import statistics
import ipaddress
from typing import List

from diagnosys.collectors.base import Collector
from diagnosys.models.network import PingMetrics

class PingCollector(Collector):
    def __init__(self, target: str = "8.8.8.8", count: int = 5, timeout_sec: float = 5):
        if not isinstance(target, str) or not target.strip() or target.startswith("-") or any(ch.isspace() for ch in target):
            raise ValueError("target must be a hostname or IP address, not an option or blank value")
        try:
            ipaddress.ip_address(target)
        except ValueError:
            if len(target) > 253 or any(
                not label or len(label) > 63
                or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
                for label in target.rstrip(".").split(".")
            ):
                raise ValueError("target must be a valid hostname or IP address")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("count must be a positive integer")
        self.target = target
        self.count = count
        self.timeout_sec = float(timeout_sec)
        if not math.isfinite(self.timeout_sec) or self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be a finite number greater than zero")
        
    def _parse_time(self, output: str) -> List[float]:
        # Preserve reply order because jitter is calculated from successive probes.
        # Less-than values are estimates, not additional exact replies.
        times = []
        pattern = r"time(=|<)([0-9]+(?:\.[0-9]+)?)\s*ms"
        for match in re.finditer(pattern, output, re.IGNORECASE):
            try:
                value = float(match.group(2))
            except ValueError:
                continue
            if not math.isfinite(value) or value < 0:
                continue
            if match.group(1) == "<":
                if value == 0:
                    continue
                value /= 2.0
            times.append(value)
        return times

    def collect(self) -> PingMetrics:
        try:
            is_windows = platform.system().lower() == "windows"
            
            # Build command
            if is_windows:
                timeout_ms = max(1, round(self.timeout_sec * 1000))
                cmd = ["ping", "-n", str(self.count), "-w", str(timeout_ms), self.target]
            else:
                timeout_seconds = max(1, math.ceil(self.timeout_sec))
                cmd = ["ping", "-c", str(self.count), "-W", str(timeout_seconds), self.target]
                
            # Run command
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout_sec * self.count + 2)
                output = result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                # If the whole command times out, treat as 100% loss
                return PingMetrics(
                    target=self.target,
                    min_ms=None, median_ms=None, p95_ms=None, max_ms=None,
                    packet_loss_percent=100.0, jitter_ms=None,
                    available=True, reason="Command timed out"
                )

            times = self._parse_time(output)
            
            # Calculate metrics
            failed_probes = self.count - len(times)
            packet_loss = max(0.0, min(100.0, (failed_probes / self.count) * 100.0))
            
            if not times:
                return PingMetrics(
                    target=self.target,
                    min_ms=None, median_ms=None, p95_ms=None, max_ms=None,
                    packet_loss_percent=packet_loss, jitter_ms=None,
                    available=True, reason="All probes failed"
                )
                
            times.sort()
            min_ms = times[0]
            max_ms = times[-1]
            median_ms = statistics.median(times)
            
            # p95
            p95_idx = int(0.95 * len(times))
            if p95_idx >= len(times):
                p95_idx = len(times) - 1
            p95_ms = times[p95_idx]
            
            # Jitter (mean of successive differences)
            jitter_ms = 0.0
            if len(times) > 1:
                # Need to use unsorted times for jitter, but we sorted them!
                # Let's re-parse for jitter to get original order.
                unsorted_times = self._parse_time(output)
                diffs = [abs(unsorted_times[i] - unsorted_times[i-1]) for i in range(1, len(unsorted_times))]
                if diffs:
                    jitter_ms = sum(diffs) / len(diffs)
                    
            return PingMetrics(
                target=self.target,
                min_ms=min_ms,
                median_ms=median_ms,
                p95_ms=p95_ms,
                max_ms=max_ms,
                packet_loss_percent=packet_loss,
                jitter_ms=jitter_ms,
                available=True
            )
            
        except Exception as e:
            return PingMetrics(
                target=self.target,
                min_ms=None, median_ms=None, p95_ms=None, max_ms=None,
                packet_loss_percent=100.0, jitter_ms=None,
                available=False, reason=f"error: {str(e)}"
            )
