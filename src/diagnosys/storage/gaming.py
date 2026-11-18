"""SQLite persistence and lifecycle tracking for opt-in game process sessions."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.collectors.system.gaming import GameSessionSnapshot
from diagnosys.storage.timestamps import serialize_timestamp


class GamingRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_snapshot(
        self,
        snapshot: GameSessionSnapshot,
        timestamp: datetime,
        system_cpu_percent: float | None = None,
        gpu_utilization_percent: float | None = None,
        gpu_temperature_c: float | None = None,
    ) -> None:
        if not snapshot.complete and not snapshot.processes:
            return
        stamp = serialize_timestamp(timestamp)
        active_names = {item.name.casefold() for item in snapshot.processes}
        if snapshot.complete:
            active_rows = self.conn.execute(
                "SELECT id, process_name FROM game_sessions WHERE ended_at IS NULL"
            ).fetchall()
            for row in active_rows:
                if row["process_name"].casefold() not in active_names:
                    self.conn.execute(
                        "UPDATE game_sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                        (stamp, row["id"]),
                    )

        for process in snapshot.processes:
            session = self.conn.execute(
                """SELECT id FROM game_sessions
                WHERE process_name = ? COLLATE NOCASE AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1""",
                (process.name,),
            ).fetchone()
            if session is None:
                cursor = self.conn.execute(
                    """INSERT INTO game_sessions(process_name, started_at, ended_at, last_seen_at)
                    VALUES (?, ?, NULL, ?)""",
                    (process.name, stamp, stamp),
                )
                session_id = int(cursor.lastrowid)
            else:
                session_id = int(session["id"])
                self.conn.execute(
                    "UPDATE game_sessions SET last_seen_at = ? WHERE id = ?",
                    (stamp, session_id),
                )
            self.conn.execute(
                """INSERT INTO game_process_samples
                (session_id, timestamp, pid, process_name, cpu_percent, memory_percent,
                 thread_count, read_bytes_per_sec, write_bytes_per_sec,
                 system_cpu_percent, gpu_utilization_percent, gpu_temperature_c)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, stamp, process.pid, process.name, process.cpu_percent,
                    process.memory_percent, process.thread_count, process.read_bytes_per_sec,
                    process.write_bytes_per_sec, system_cpu_percent,
                    gpu_utilization_percent, gpu_temperature_c,
                ),
            )
        self.conn.commit()

    def query_sessions(self, window_seconds: int = 30 * 86400, limit: int = 100) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=max(1, window_seconds)))
        rows = self.conn.execute(
            """SELECT s.id, s.process_name, s.started_at, s.ended_at, s.last_seen_at,
            COUNT(p.id) AS sample_count,
            MAX(p.cpu_percent) AS peak_process_cpu_percent,
            AVG(p.cpu_percent) AS average_process_cpu_percent,
            MAX(p.memory_percent) AS peak_memory_percent,
            AVG(p.memory_percent) AS average_memory_percent,
            MAX(p.system_cpu_percent) AS peak_system_cpu_percent,
            AVG(p.system_cpu_percent) AS average_system_cpu_percent,
            MAX(p.gpu_utilization_percent) AS peak_gpu_utilization_percent,
            AVG(p.gpu_utilization_percent) AS average_gpu_utilization_percent
            FROM game_sessions s LEFT JOIN game_process_samples p ON p.session_id = s.id
            WHERE s.started_at >= ?
            GROUP BY s.id ORDER BY s.started_at DESC LIMIT ?""",
            (cutoff, max(1, min(limit, 1000))),
        ).fetchall()
        return [dict(row) for row in rows]

    def query_samples(self, session_id: int, limit: int = 1000) -> list[dict]:
        rows = self.conn.execute(
            """SELECT timestamp, pid, process_name, cpu_percent, memory_percent,
            thread_count, read_bytes_per_sec, write_bytes_per_sec,
            system_cpu_percent, gpu_utilization_percent, gpu_temperature_c
            FROM game_process_samples WHERE session_id = ?
            ORDER BY timestamp DESC LIMIT ?""",
            (session_id, max(1, min(limit, 10000))),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def latest_samples(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            """SELECT timestamp, session_id, pid, process_name, cpu_percent, memory_percent,
            thread_count, read_bytes_per_sec, write_bytes_per_sec,
            system_cpu_percent, gpu_utilization_percent, gpu_temperature_c
            FROM game_process_samples ORDER BY timestamp DESC LIMIT ?""",
            (max(1, min(limit, 1000)),),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
