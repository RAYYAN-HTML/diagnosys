from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Anomaly:
    timestamp: datetime
    category: str
    severity: str
    metric: str
    observed_value: float
    expected_value: float
    rule_id: str
    explanation: str

@dataclass
class Evidence:
    metric: str
    observed_value: float
    expected_value: float
    time_window: int
    direction: str
    strength: str

@dataclass
class DiagnosisHypothesis:
    category: str
    score: float
    confidence: str
    evidence: List[Evidence] = field(default_factory=list)
    contradictory_evidence: List[Evidence] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    recommended_checks: List[str] = field(default_factory=list)

@dataclass
class DiagnosisResult:
    status: str
    primary_hypothesis: Optional[DiagnosisHypothesis]
    alternatives: List[DiagnosisHypothesis] = field(default_factory=list)
    time_window: int = 60
    generated_at: datetime = field(default_factory=datetime.utcnow)
    data_quality: str = "GOOD"
