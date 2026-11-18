"""Evidence-first deterministic diagnosis. No probability or confidence scores."""
from __future__ import annotations
from collections import defaultdict
from typing import List
from diagnosys.correlation.engine import CorrelationEngine
from diagnosys.models.diagnostics import Anomaly, DiagnosisHypothesis, DiagnosisResult, Evidence

class DiagnosticEngine:
    RESOURCE = {"CPU_PRESSURE", "MEMORY_PRESSURE", "DISK_PRESSURE"}
    NETWORK = {"NETWORK_LATENCY", "NETWORK_JITTER", "PACKET_LOSS", "DNS_LATENCY", "HTTP_LATENCY"}

    def __init__(self):
        self.correlation_engine = CorrelationEngine()

    def diagnose(self, anomalies: List[Anomaly], window_seconds: int = 60) -> DiagnosisResult:
        # Ignore legacy anomaly rows created by the former global-cutoff engine.
        anomalies = [item for item in anomalies if item.rule_id.endswith("_personal_baseline_deviation")]
        if not anomalies:
            return DiagnosisResult(status="NO_ANOMALY", primary_hypothesis=None,
                                   time_window=window_seconds, data_quality="BASELINE_RELATIVE")
        groups = defaultdict(list)
        for item in anomalies:
            if item.category in self.RESOURCE:
                groups["LOCAL_RESOURCE_CONTENTION"].append(item)
            elif item.category in self.NETWORK:
                groups["NETWORK_INSTABILITY"].append(item)
            else:
                groups[f"OBSERVED_{item.category}"].append(item)
        correlations = self.correlation_engine.correlate(anomalies)
        hypotheses = []
        for category, observations in groups.items():
            evidence = [
                Evidence(metric=item.metric, observed_value=item.observed_value,
                         expected_value=item.expected_value, time_window=window_seconds,
                         direction="HIGH",
                         strength="Repeated observation" if sum(x.metric == item.metric for x in observations) > 1 else "Single observation")
                for item in observations
            ]
            limitations = [
                "A baseline deviation identifies unusual behaviour, not necessarily a fault.",
                "Time overlap and shared symptoms do not prove that one signal caused another.",
                *correlations,
            ]
            hypotheses.append(DiagnosisHypothesis(
                category=category, evidence=evidence,
                limitations=list(dict.fromkeys(limitations)),
                recommended_checks=self._checks(category, observations),
            ))
        # Transparent ordering by observed evidence count, not a confidence score.
        hypotheses.sort(key=lambda item: (-len(item.evidence), item.category))
        return DiagnosisResult(status="INVESTIGATE", primary_hypothesis=hypotheses[0],
                               alternatives=hypotheses[1:], time_window=window_seconds,
                               data_quality="BASELINE_RELATIVE")

    @staticmethod
    def _checks(category: str, observations: list[Anomaly]) -> list[str]:
        metrics = {item.metric for item in observations}
        if category == "LOCAL_RESOURCE_CONTENTION":
            checks = []
            if "cpu_percent" in metrics:
                checks.append("Inspect the process timeline and per-core CPU activity during the same interval.")
            if "memory_percent" in metrics:
                checks.append("Inspect the largest memory consumers and available memory over time.")
            if "disk_percent" in metrics:
                checks.append("Check the affected volume's free space and storage health.")
            checks.append("Compare the same workload against a later capture to see whether the deviation persists.")
            return checks
        if category == "NETWORK_INSTABILITY":
            return [
                "Repeat the measurement against the local gateway and a second independent destination.",
                "Compare DNS, latency, jitter, and packet loss before changing network settings.",
                "Check whether the issue affects one destination or multiple services.",
            ]
        return ["Collect another sample and inspect the raw evidence for this metric."]
