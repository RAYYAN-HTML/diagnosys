"""Models for user captured diagnostic incidents."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Incident:
    id: int | None
    started_at: datetime
    ended_at: datetime
    title: str
    summary: str
    metrics_count: int
    anomalies_count: int
    diagnosis_category: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    symptom: str = "other"
    status: str = "captured"
    resolution_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "title": self.title,
            "summary": self.summary,
            "metrics_count": self.metrics_count,
            "anomalies_count": self.anomalies_count,
            "diagnosis_category": self.diagnosis_category,
            "evidence": self.evidence,
            "symptom": self.symptom,
            "status": self.status,
            "resolution_note": self.resolution_note,
        }
