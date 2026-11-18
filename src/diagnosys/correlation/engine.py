"""Time-window correlation that reports overlap without claiming causation."""
from __future__ import annotations
from datetime import timezone
from typing import List
from diagnosys.models.diagnostics import Anomaly

class CorrelationEngine:
    def __init__(self, time_window: int = 60):
        self.time_window = max(1, int(time_window))

    @staticmethod
    def _seconds(anomaly: Anomaly) -> float:
        value = anomaly.timestamp
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()

    def _overlap(self, left: list[Anomaly], right: list[Anomaly]) -> bool:
        return any(abs(self._seconds(a) - self._seconds(b)) <= self.time_window for a in left for b in right)

    def correlate(self, anomalies: List[Anomaly]) -> List[str]:
        cpu = [x for x in anomalies if x.category == "CPU_PRESSURE"]
        memory = [x for x in anomalies if x.category == "MEMORY_PRESSURE"]
        disk = [x for x in anomalies if x.category == "DISK_PRESSURE"]
        network = [x for x in anomalies if x.category in {"NETWORK_LATENCY", "NETWORK_JITTER", "PACKET_LOSS", "DNS_LATENCY", "HTTP_LATENCY"}]
        insights = []
        if self._overlap(cpu, network):
            insights.append("CPU and network deviations overlapped in time; this is correlation, not proof that CPU activity caused network delay.")
        if self._overlap(cpu, disk):
            insights.append("CPU and disk deviations overlapped in time; inspect process and disk activity together.")
        if self._overlap(memory, disk):
            insights.append("Memory and disk deviations overlapped in time; inspect paging and storage activity together.")
        return insights
