from typing import List
from diagnosys.models.diagnostics import Anomaly, DiagnosisResult, DiagnosisHypothesis, Evidence
from diagnosys.correlation.engine import CorrelationEngine

class DiagnosticEngine:
    def __init__(self):
        self.correlation_engine = CorrelationEngine()
        
    def diagnose(self, anomalies: List[Anomaly], window_seconds: int = 60) -> DiagnosisResult:
        if not anomalies:
            return DiagnosisResult(
                status="HEALTHY",
                primary_hypothesis=DiagnosisHypothesis(
                    category="HEALTHY",
                    score=1.0,
                    confidence="High",
                    evidence=[],
                    recommended_checks=["Run monitor for a longer period if issues persist."]
                ),
                time_window=window_seconds
            )
            
        insights = self.correlation_engine.correlate(anomalies)
        categories = {anomaly.category for anomaly in anomalies}
        correlation_limits = [
            f"{insight} These signals overlap in time but do not prove causation."
            for insight in insights
        ]
        hypotheses: list[DiagnosisHypothesis] = []

        resource_categories = {"CPU_PRESSURE", "MEMORY_PRESSURE", "DISK_PRESSURE"}
        resource_anomalies = [anomaly for anomaly in anomalies if anomaly.category in resource_categories]
        if resource_anomalies:
            evidence = [
                Evidence(
                    metric=anomaly.metric,
                    observed_value=anomaly.observed_value,
                    expected_value=anomaly.expected_value,
                    time_window=window_seconds,
                    direction="HIGH",
                    strength="Moderate",
                )
                for anomaly in resource_anomalies
            ]
            resource_metrics = {anomaly.metric for anomaly in resource_anomalies}
            checks = []
            if "CPU_PRESSURE" in categories:
                checks.append("Review Overview → Top processes for an unusually busy application.")
            if "MEMORY_PRESSURE" in categories:
                checks.append("Review the highest-memory processes and close anything you do not need.")
            if "DISK_PRESSURE" in categories:
                checks.append("Check free space on the system drive and remove or move files if it is nearly full.")
            hypotheses.append(DiagnosisHypothesis(
                category="LOCAL_RESOURCE_CONTENTION",
                score=min(0.92, 0.62 + 0.12 * (len(resource_metrics) - 1)),
                confidence="High" if len(resource_metrics) >= 2 else "Moderate",
                evidence=evidence,
                limitations=correlation_limits + [
                    "Measurements show resource pressure but may not identify its underlying cause."
                ],
                recommended_checks=checks,
            ))

        network_categories = {
            "NETWORK_LATENCY", "NETWORK_JITTER", "PACKET_LOSS", "DNS_LATENCY", "HTTP_LATENCY"
        }
        network_anomalies = [anomaly for anomaly in anomalies if anomaly.category in network_categories]
        if network_anomalies:
            evidence = [
                Evidence(
                    metric=anomaly.metric,
                    observed_value=anomaly.observed_value,
                    expected_value=anomaly.expected_value,
                    time_window=window_seconds,
                    direction="HIGH",
                    strength="Moderate",
                )
                for anomaly in network_anomalies
            ]
            network_domains = {
                "ping" if anomaly.metric in {"ping_median_ms", "ping_jitter_ms", "packet_loss_percent"}
                else anomaly.metric.removesuffix("_latency_ms")
                for anomaly in network_anomalies
            }
            hypotheses.append(DiagnosisHypothesis(
                category="NETWORK_INSTABILITY",
                score=min(0.92, 0.62 + 0.12 * (len(network_domains) - 1)),
                confidence="High" if len(network_domains) >= 2 else "Moderate",
                evidence=evidence,
                limitations=correlation_limits + [
                    "A network check measures the selected destination and may not represent every service."
                ],
                recommended_checks=[
                    "Repeat the check and compare another destination.",
                    "If only one service is affected, check that service before changing network settings.",
                ],
            ))

        if not hypotheses:
            hypotheses.append(DiagnosisHypothesis(
                category="UNKNOWN_ANOMALY",
                score=0.5,
                confidence="Low",
                evidence=[],
                limitations=correlation_limits,
                recommended_checks=["Review the recent anomaly details and collect another sample."],
            ))

        hypotheses.sort(key=lambda hypothesis: hypothesis.score, reverse=True)
        return DiagnosisResult(
            status="WARNING",
            primary_hypothesis=hypotheses[0],
            alternatives=hypotheses[1:],
            time_window=window_seconds
        )
