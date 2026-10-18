from dataclasses import dataclass, field
from typing import List, Dict, Any
from datetime import datetime
from diagnosys.models.baselines import MetricBaseline
from diagnosys.models.diagnostics import Anomaly, DiagnosisResult

@dataclass
class DiagnosticReport:
    timestamp: datetime
    system_info: Dict[str, Any]
    baselines: List[MetricBaseline]
    recent_anomalies: List[Anomaly]
    diagnoses: DiagnosisResult
    process_activity: List[Dict[str, Any]] = field(default_factory=list)
    recent_incidents: List[Dict[str, Any]] = field(default_factory=list)
