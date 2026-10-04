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
        
        # Build hypotheses
        hypotheses = []
        
        categories = set(a.category for a in anomalies)
        
        if "CPU_PRESSURE" in categories:
            evidence = [
                Evidence(
                    metric=a.metric,
                    observed_value=a.observed_value,
                    expected_value=a.expected_value,
                    time_window=window_seconds,
                    direction="HIGH",
                    strength="High"
                ) for a in anomalies if a.category == "CPU_PRESSURE"
            ]
            
            hypotheses.append(DiagnosisHypothesis(
                category="LOCAL_RESOURCE_CONTENTION",
                score=0.8,
                confidence="High",
                evidence=evidence,
                limitations=["Cannot identify the specific application causing pressure from metrics alone."],
                recommended_checks=["Check 'diagnosys processes' to identify the CPU consumer."]
            ))
            
        if "NETWORK_LATENCY" in categories or "PACKET_LOSS" in categories:
            hypotheses.append(DiagnosisHypothesis(
                category="NETWORK_INSTABILITY",
                score=0.85,
                confidence="High",
                evidence=[],
                recommended_checks=["Test another known-good network."]
            ))
            
        if not hypotheses:
            hypotheses.append(DiagnosisHypothesis(
                category="UNKNOWN_ANOMALY",
                score=0.5,
                confidence="Low",
                evidence=[]
            ))
            
        # Sort hypotheses by score
        hypotheses.sort(key=lambda h: h.score, reverse=True)
        
        return DiagnosisResult(
            status="WARNING" if hypotheses else "HEALTHY",
            primary_hypothesis=hypotheses[0],
            alternatives=hypotheses[1:],
            time_window=window_seconds
        )
