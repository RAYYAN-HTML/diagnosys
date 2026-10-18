"""Persistence for captured diagnostic incidents."""

import sqlite3
import json
from datetime import datetime, timezone

from diagnosys.models.incidents import Incident
from diagnosys.storage.timestamps import parse_timestamp, serialize_timestamp


class IncidentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, incident: Incident) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO incidents
            (started_at, ended_at, title, summary, metrics_count, anomalies_count,
             diagnosis_category, evidence_json, symptom, status, resolution_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (serialize_timestamp(incident.started_at), serialize_timestamp(incident.ended_at),
             incident.title, incident.summary,
             incident.metrics_count, incident.anomalies_count, incident.diagnosis_category,
             json.dumps(incident.evidence, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)),
             incident.symptom, incident.status, incident.resolution_note),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def start_investigation(self, symptom: str, title: str) -> int:
        """Persist a problem marker before evidence collection begins."""
        now = datetime.now(timezone.utc)
        cursor = self.conn.execute(
            """INSERT INTO incidents
            (started_at, ended_at, title, summary, metrics_count, anomalies_count,
             diagnosis_category, evidence_json, symptom, status, resolution_note)
            VALUES (?, ?, ?, ?, 0, 0, NULL, ?, ?, 'investigating', '')""",
            (serialize_timestamp(now), serialize_timestamp(now), title,
             "Investigation is collecting evidence.", json.dumps({"markers": []}), symptom),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_marker(self, incident_id: int, marker: dict) -> None:
        row = self.conn.execute(
            "SELECT evidence_json FROM incidents WHERE id = ? AND status = 'investigating'",
            (incident_id,),
        ).fetchone()
        if row is None:
            return
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        evidence.setdefault("markers", []).append(marker)
        self.conn.execute(
            "UPDATE incidents SET evidence_json = ? WHERE id = ?",
            (json.dumps(evidence, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)), incident_id),
        )
        self.conn.commit()

    def finish_investigation(
        self,
        incident_id: int,
        ended_at: datetime,
        summary: str,
        metrics_count: int,
        anomalies_count: int,
        diagnosis_category: str | None,
        evidence: dict,
    ) -> None:
        self.conn.execute(
            """UPDATE incidents SET ended_at = ?, summary = ?, metrics_count = ?,
            anomalies_count = ?, diagnosis_category = ?, evidence_json = ?, status = 'captured'
            WHERE id = ? AND status = 'investigating'""",
            (serialize_timestamp(ended_at), summary, metrics_count, anomalies_count,
             diagnosis_category, json.dumps(evidence, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)),
             incident_id),
        )
        self.conn.commit()

    def set_resolution(self, incident_id: int, status: str, note: str = "") -> None:
        if status not in {"resolved", "still_happening", "captured"}:
            raise ValueError("status must be resolved, still_happening, or captured")
        self.conn.execute(
            "UPDATE incidents SET status = ?, resolution_note = ? WHERE id = ? AND status != 'investigating'",
            (status, note.strip(), incident_id),
        )
        self.conn.commit()

    def begin_verification(self, incident_id: int, note: str = "") -> datetime:
        now = datetime.now(timezone.utc)
        row = self.conn.execute(
            "SELECT evidence_json FROM incidents WHERE id = ? AND status != 'investigating'",
            (incident_id,),
        ).fetchone()
        if row is None:
            raise ValueError("The incident is not available for verification.")
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        resuming = bool(evidence.get("verification_started_at") and not evidence.get("verification"))
        evidence["verification_started_at"] = now.isoformat()
        evidence["verification_note"] = note.strip()
        evidence.pop("verification", None)
        evidence.setdefault("markers", []).append({
            "timestamp": now.isoformat(),
            "kind": "after-change check resumed" if resuming else "after-change check started",
            "text": "A new one-minute measurement window began after Diagnosys reopened." if resuming else (note.strip() or "User started a one-minute after-change check."),
        })
        self.conn.execute(
            "UPDATE incidents SET evidence_json = ?, status = 'captured', resolution_note = ? WHERE id = ?",
            (json.dumps(evidence, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)), note.strip(), incident_id),
        )
        self.conn.commit()
        return now

    def save_verification(self, incident_id: int, verification: dict) -> None:
        row = self.conn.execute("SELECT evidence_json FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            return
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        evidence["verification"] = verification
        self.conn.execute(
            "UPDATE incidents SET evidence_json = ? WHERE id = ?",
            (json.dumps(evidence, default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value)), incident_id),
        )
        self.conn.commit()

    def active_investigation(self) -> Incident | None:
        cursor = self.conn.execute(
            "SELECT * FROM incidents WHERE status = 'investigating' ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return self._from_row(row) if row else None

    def query(self, limit: int = 20) -> list[Incident]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM incidents ORDER BY started_at DESC LIMIT ?", (limit,))
        return [self._from_row(row) for row in cursor.fetchall()]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Incident:
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            evidence = {}
        keys = set(row.keys())
        return Incident(
            id=row["id"], started_at=parse_timestamp(row["started_at"]),
            ended_at=parse_timestamp(row["ended_at"]),
            title=row["title"], summary=row["summary"],
            metrics_count=row["metrics_count"], anomalies_count=row["anomalies_count"],
            diagnosis_category=row["diagnosis_category"], evidence=evidence,
            symptom=row["symptom"] if "symptom" in keys else "other",
            status=row["status"] if "status" in keys else "captured",
            resolution_note=row["resolution_note"] if "resolution_note" in keys else "",
        )
