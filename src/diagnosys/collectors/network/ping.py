import subprocess
import platform
import re
import statistics
from typing import List

from diagnosys.collectors.base import Collector
from diagnosys.models.network import PingMetrics

class PingCollector(Collector):
    def __init__(self, target: str = "8.8.8.8", count: int = 5, timeout_sec: int = 5):
        self.target = target
        self.count = count
        self.timeout_sec = timeout_sec
        
    def _parse_time(self, output: str) -> List[float]:
        # Matches: time=14ms, time=14.2 ms, time<1ms (which we'll treat as 0.5)
        times = []
        for match in re.finditer(r"time[=<]([0-9.]+) ?ms", output, re.IGNORECASE):
            val = match.group(1)
            try:
                times.append(float(val))
            except ValueError:
                pass
                
        # Handle Windows 'time<1ms'
        for match in re.finditer(r"time<1ms", output, re.IGNORECASE):
            times.append(0.5)
            
        return times

    def collect(self) -> PingMetrics:
        try:
            is_windows = platform.system().lower() == "windows"
            
            # Build command
            if is_windows:
                cmd = ["ping", "-n", str(self.count), "-w", str(self.timeout_sec * 1000), self.target]
            else:
                cmd = ["ping", "-c", str(self.count), "-W", str(self.timeout_sec), self.target]
                
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
