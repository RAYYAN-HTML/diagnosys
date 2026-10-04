from typing import List, Optional
from datetime import datetime, timezone

from diagnosys.models.metrics import MetricSample
from diagnosys.models.diagnostics import Anomaly

class AnomalyDetector:
    def __init__(self):
        # Configurable thresholds
        self.cpu_threshold = 85.0
        self.memory_threshold = 90.0
        self.disk_threshold = 95.0
        
    def detect_cpu_spike(self, sample: MetricSample) -> Optional[Anomaly]:
        if sample.metric_name == "cpu_percent" and sample.value > self.cpu_threshold:
            return Anomaly(
                timestamp=sample.timestamp,
                category="CPU_PRESSURE",
                severity="WARNING",
                metric=sample.metric_name,
                observed_value=sample.value,
                expected_value=self.cpu_threshold,
                rule_id="cpu_spike_85",
                explanation=f"CPU utilization spiked to {sample.value:.1f}%"
            )
        return None
        
    def detect_memory_pressure(self, sample: MetricSample) -> Optional[Anomaly]:
        if sample.metric_name == "memory_percent" and sample.value > self.memory_threshold:
            return Anomaly(
                timestamp=sample.timestamp,
                category="MEMORY_PRESSURE",
                severity="WARNING",
                metric=sample.metric_name,
                observed_value=sample.value,
                expected_value=self.memory_threshold,
                rule_id="mem_pressure_90",
                explanation=f"Memory utilization reached {sample.value:.1f}%"
            )
        return None
        
    def evaluate_sample(self, sample: MetricSample) -> List[Anomaly]:
        anomalies = []
        if a := self.detect_cpu_spike(sample):
            anomalies.append(a)
        if a := self.detect_memory_pressure(sample):
            anomalies.append(a)
            
        return anomalies
