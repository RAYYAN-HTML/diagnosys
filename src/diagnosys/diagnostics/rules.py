from typing import List, Optional, Dict
from diagnosys.models.metrics import MetricSample, MetricStatus
from diagnosys.models.diagnostics import Anomaly
from diagnosys.models.baselines import MetricBaseline

class AnomalyDetector:
    def __init__(
        self,
        baselines: Optional[Dict[str, MetricBaseline]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        baseline_deviation_pct: float = 20.0,
    ):
        # Configurable hardcoded thresholds (used when no baseline is available)
        configured = thresholds or {}
        self.cpu_threshold = float(configured.get("cpu_percent", 85.0))
        self.memory_threshold = float(configured.get("memory_percent", 90.0))
        self.disk_threshold = float(configured.get("disk_percent", 95.0))
        # How many percentage points above baseline p95 to consider an anomaly
        self.baseline_deviation_pct = float(baseline_deviation_pct)
        self.baselines = baselines or {}

    def _get_threshold(self, metric_name: str, hardcoded: float) -> tuple[float, str]:
        """
        Returns (threshold, rule_source).
        If a valid baseline exists, the threshold is baseline p95 + deviation margin.
        Otherwise falls back to the hardcoded threshold.
        """
        baseline = self.baselines.get(metric_name)
        if baseline and baseline.available and baseline.sample_count >= 5:
            dynamic = baseline.p95 + self.baseline_deviation_pct
            return (dynamic, 'baseline')
        return (hardcoded, 'hardcoded')

    def detect_cpu_spike(self, sample: MetricSample) -> Optional[Anomaly]:
        if sample.metric_name != "cpu_percent":
            return None
        threshold, source = self._get_threshold("cpu_percent", self.cpu_threshold)
        if sample.value > threshold:
            return Anomaly(
                timestamp=sample.timestamp,
                category="CPU_PRESSURE",
                severity="WARNING",
                metric=sample.metric_name,
                observed_value=sample.value,
                expected_value=threshold,
                rule_id=f"cpu_spike_{source}",
                explanation=f"CPU utilization spiked to {sample.value:.1f}% (threshold: {threshold:.1f}% [{source}])"
            )
        return None

    def detect_memory_pressure(self, sample: MetricSample) -> Optional[Anomaly]:
        if sample.metric_name != "memory_percent":
            return None
        threshold, source = self._get_threshold("memory_percent", self.memory_threshold)
        if sample.value > threshold:
            return Anomaly(
                timestamp=sample.timestamp,
                category="MEMORY_PRESSURE",
                severity="WARNING",
                metric=sample.metric_name,
                observed_value=sample.value,
                expected_value=threshold,
                rule_id=f"mem_pressure_{source}",
                explanation=f"Memory utilization reached {sample.value:.1f}% (threshold: {threshold:.1f}% [{source}])"
            )
        return None

    def detect_disk_pressure(self, sample: MetricSample) -> Optional[Anomaly]:
        if sample.metric_name != "disk_percent":
            return None
        threshold, source = self._get_threshold("disk_percent", self.disk_threshold)
        if sample.value > threshold:
            return Anomaly(
                timestamp=sample.timestamp,
                category="DISK_PRESSURE",
                severity="WARNING",
                metric=sample.metric_name,
                observed_value=sample.value,
                expected_value=threshold,
                rule_id=f"disk_pressure_{source}",
                explanation=f"Disk usage reached {sample.value:.1f}% (threshold: {threshold:.1f}% [{source}])"
            )
        return None

    def _detect_above_threshold(
        self,
        sample: MetricSample,
        metric_name: str,
        category: str,
        hardcoded_threshold: float,
        rule_prefix: str,
        description: str,
    ) -> Optional[Anomaly]:
        if sample.metric_name != metric_name or sample.status != MetricStatus.OK or sample.value is None:
            return None
        # Network measurements have different units and much smaller sample
        # counts than system metrics, so keep their thresholds explicit.
        threshold, source = hardcoded_threshold, "hardcoded"
        value = float(sample.value)
        if value <= threshold:
            return None
        return Anomaly(
            timestamp=sample.timestamp,
            category=category,
            severity="WARNING",
            metric=metric_name,
            observed_value=value,
            expected_value=threshold,
            rule_id=f"{rule_prefix}_{source}",
            explanation=f"{description} reached {value:.1f}{sample.unit} (threshold: {threshold:.1f}{sample.unit} [{source}])",
        )

    def detect_ping_latency(self, sample: MetricSample) -> Optional[Anomaly]:
        return self._detect_above_threshold(
            sample, "ping_median_ms", "NETWORK_LATENCY", 150.0,
            "ping_latency", "Median ping latency",
        )

    def detect_packet_loss(self, sample: MetricSample) -> Optional[Anomaly]:
        return self._detect_above_threshold(
            sample, "packet_loss_percent", "PACKET_LOSS", 2.0,
            "packet_loss", "Packet loss",
        )

    def detect_ping_jitter(self, sample: MetricSample) -> Optional[Anomaly]:
        return self._detect_above_threshold(
            sample, "ping_jitter_ms", "NETWORK_JITTER", 30.0,
            "ping_jitter", "Ping jitter",
        )

    def detect_dns_latency(self, sample: MetricSample) -> Optional[Anomaly]:
        return self._detect_above_threshold(
            sample, "dns_latency_ms", "DNS_LATENCY", 1000.0,
            "dns_latency", "DNS resolution latency",
        )

    def detect_http_latency(self, sample: MetricSample) -> Optional[Anomaly]:
        return self._detect_above_threshold(
            sample, "http_latency_ms", "HTTP_LATENCY", 1500.0,
            "http_latency", "HTTP response latency",
        )

    def evaluate_sample(self, sample: MetricSample) -> List[Anomaly]:
        if sample.status != MetricStatus.OK:
            return []
        anomalies = []
        for detector in [
            self.detect_cpu_spike,
            self.detect_memory_pressure,
            self.detect_disk_pressure,
            self.detect_ping_latency,
            self.detect_packet_loss,
            self.detect_ping_jitter,
            self.detect_dns_latency,
            self.detect_http_latency,
        ]:
            if a := detector(sample):
                anomalies.append(a)
        return anomalies
