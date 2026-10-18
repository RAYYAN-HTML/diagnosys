from diagnosys.ai.provider import DummyAIProvider
from diagnosys.models.diagnostics import DiagnosisResult, DiagnosisHypothesis
from datetime import datetime

def test_dummy_ai_provider():
    provider = DummyAIProvider()
    
    # Healthy case
    healthy_result = DiagnosisResult(
        status="HEALTHY",
        primary_hypothesis=None,
        alternatives=[],
        time_window=3600,
        generated_at=datetime.now(),
        data_quality="GOOD"
    )
    assert "healthy" in provider.explain(healthy_result).lower()
    
    # Unhealthy case
    unhealthy_result = DiagnosisResult(
        status="WARNING",
        primary_hypothesis=DiagnosisHypothesis(
            category="NETWORK_LATENCY",
            score=0.9,
            confidence="High",
            evidence=[],
            contradictory_evidence=[],
            limitations=[],
            recommended_checks=[]
        ),
        alternatives=[],
        time_window=3600,
        generated_at=datetime.now(),
        data_quality="GOOD"
    )
    
    explanation = provider.explain(unhealthy_result)
    assert "Network Latency" in explanation
