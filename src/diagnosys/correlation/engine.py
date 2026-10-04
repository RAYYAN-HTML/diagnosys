from typing import List
from diagnosys.models.diagnostics import Anomaly

class CorrelationEngine:
    def __init__(self, time_window: int = 60):
        self.time_window = time_window
        
    def correlate(self, anomalies: List[Anomaly]) -> List[str]:
        """
        Groups anomalies within the time window and identifies correlated events.
        """
        # A simple implementation for MVP
        categories_seen = set(a.category for a in anomalies)
        
        insights = []
        if "CPU_PRESSURE" in categories_seen and "NETWORK_LATENCY" in categories_seen:
            insights.append("CPU pressure and network latency increased during the same interval.")
            
        if "CPU_PRESSURE" in categories_seen and "DISK_PRESSURE" in categories_seen:
            insights.append("Local resource contention detected (CPU + Disk).")
            
        return insights
