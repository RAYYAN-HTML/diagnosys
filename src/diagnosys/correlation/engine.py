from typing import List
from datetime import timezone
from diagnosys.models.diagnostics import Anomaly

class CorrelationEngine:
    def __init__(self, time_window: int = 60):
        self.time_window = time_window
        
    def correlate(self, anomalies: List[Anomaly]) -> List[str]:
        """
        Groups anomalies within the time window and identifies correlated events.
        """
        insights = []
        cpu_events = [anomaly for anomaly in anomalies if anomaly.category == "CPU_PRESSURE"]
        network_events = [
            anomaly for anomaly in anomalies
            if anomaly.category in {"NETWORK_LATENCY", "NETWORK_JITTER", "PACKET_LOSS", "DNS_LATENCY", "HTTP_LATENCY"}
        ]
        disk_events = [anomaly for anomaly in anomalies if anomaly.category == "DISK_PRESSURE"]

        def timestamp_seconds(anomaly: Anomaly) -> float:
            timestamp = anomaly.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return timestamp.timestamp()

        def overlap(left_events: list[Anomaly], right_events: list[Anomaly]) -> bool:
            return any(
                abs(timestamp_seconds(left) - timestamp_seconds(right)) <= self.time_window
                for left in left_events
                for right in right_events
            )

        if overlap(cpu_events, network_events):
            insights.append("CPU pressure and network instability appeared during the same interval.")

        if overlap(cpu_events, disk_events):
            insights.append("Local resource contention detected (CPU + Disk).")

        return insights
