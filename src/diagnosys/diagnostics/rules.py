"""Baseline-relative anomaly rules. No global performance cutoffs."""
from __future__ import annotations
from typing import Dict, List, Optional
from diagnosys.models.baselines import MetricBaseline
from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.metrics import MetricSample, MetricStatus

class AnomalyDetector:
    MIN_BASELINE_SAMPLES = 30
    MAD_SCALE = 1.4826
    DEVIATION_MULTIPLIER = 3.0
    METRICS = {
        "cpu_percent": ("CPU_PRESSURE", "CPU utilization"),
        "memory_percent": ("MEMORY_PRESSURE", "Memory utilization"),
        "disk_percent": ("DISK_PRESSURE", "Disk space utilization"),
        "ping_median_ms": ("NETWORK_LATENCY", "Median ping latency"),
        "packet_loss_percent": ("PACKET_LOSS", "Packet loss"),
        "ping_jitter_ms": ("NETWORK_JITTER", "Ping jitter"),
        "dns_latency_ms": ("DNS_LATENCY", "DNS resolution latency"),
        "http_latency_ms": ("HTTP_LATENCY", "HTTP response latency"),
    }

    def __init__(self, baselines: Optional[Dict[str, MetricBaseline]] = None):
        self.baselines = baselines or {}

    def evaluate_sample(self, sample: MetricSample) -> List[Anomaly]:
        if sample.status != MetricStatus.OK or sample.value is None:
            return []
        definition = self.METRICS.get(sample.metric_name)
        baseline = self.baselines.get(sample.metric_name)
        if not definition or not baseline or not baseline.available or baseline.sample_count < self.MIN_BASELINE_SAMPLES:
            return []
        category, label = definition
        observed = float(sample.value)
        # The comparison band is learned from the device's own history.
        robust_band = baseline.median + self.DEVIATION_MULTIPLIER * self.MAD_SCALE * baseline.mad
        expected = max(baseline.p95, robust_band)
        if observed <= expected:
            return []
        return [Anomaly(
            timestamp=sample.timestamp, category=category, severity="WARNING",
            metric=sample.metric_name, observed_value=observed, expected_value=expected,
            rule_id=f"{sample.metric_name}_personal_baseline_deviation",
            explanation=f"{label} is outside this device's learned variation band ({observed:.2f}{sample.unit}; personal upper band {expected:.2f}{sample.unit}).",
        )]
