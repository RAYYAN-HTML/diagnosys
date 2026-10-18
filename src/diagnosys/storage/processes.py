"""Persistence for lightweight, privacy-conscious process history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.models.metrics import ProcessSnapshot
from diagnosys.storage.timestamps import serialize_timestamp


class ProcessRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_snapshot(self, snapshot: ProcessSnapshot) -> None:
        if not snapshot.available:
            return
        samples = {}
        for process in (*snapshot.top_cpu, *snapshot.top_memory):
            samples[process.pid] = process
        timestamp = serialize_timestamp(snapshot.timestamp)
        self.conn.executemany(
            """INSERT INTO process_samples
            (timestamp, pid, process_name, cpu_percent, memory_percent,
             read_bytes_per_sec, write_bytes_per_sec, network_connection_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    timestamp, process.pid, process.name, process.cpu_percent, process.memory_percent,
                    process.read_bytes_per_sec, process.write_bytes_per_sec,
                    process.network_connection_count,
                )
                for process in samples.values()
            ],
        )
        self.conn.commit()

    def query(self, window_seconds: int = 86400, limit: int = 5000) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds))
        cursor = self.conn.execute(
            """SELECT timestamp, pid, process_name, cpu_percent, memory_percent,
            read_bytes_per_sec, write_bytes_per_sec, network_connection_count
            FROM process_samples WHERE timestamp >= ?
            ORDER BY timestamp DESC LIMIT ?""",
            (cutoff, max(1, min(limit, 50000))),
        )
        return [dict(row) for row in cursor.fetchall()]

    def query_between(self, start: datetime, end: datetime, limit: int = 50000) -> list[dict]:
        cursor = self.conn.execute(
            """SELECT timestamp, pid, process_name, cpu_percent, memory_percent,
            read_bytes_per_sec, write_bytes_per_sec, network_connection_count
            FROM process_samples WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC LIMIT ?""",
            (serialize_timestamp(start), serialize_timestamp(end), max(1, min(limit, 250000))),
        )
        return [dict(row) for row in cursor.fetchall()]

    def top_processes(self, window_seconds: int = 3600, limit: int = 10) -> list[dict]:
        cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(seconds=window_seconds))
        cursor = self.conn.execute(
            """SELECT process_name, MAX(cpu_percent) AS peak_cpu_percent,
            MAX(memory_percent) AS peak_memory_percent,
            MAX(read_bytes_per_sec) AS peak_read_bytes_per_sec,
            MAX(write_bytes_per_sec) AS peak_write_bytes_per_sec,
            MAX(network_connection_count) AS peak_network_connections, COUNT(*) AS samples
            FROM process_samples WHERE timestamp >= ?
            GROUP BY process_name ORDER BY peak_cpu_percent DESC LIMIT ?""",
            (cutoff, max(1, min(limit, 100))),
        )
        return [dict(row) for row in cursor.fetchall()]
