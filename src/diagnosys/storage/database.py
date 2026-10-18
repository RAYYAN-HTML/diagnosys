import sqlite3
import os
from datetime import datetime, timedelta, timezone
from diagnosys.config.settings import Settings
from diagnosys.storage.timestamps import parse_timestamp, serialize_timestamp

def get_db_path(memory: bool = False) -> str:
    if memory:
        return ":memory:"
    
    data_dir = Settings.from_env().data_dir
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "diagnosys.sqlite")

def get_connection(memory: bool = False) -> sqlite3.Connection:
    path = get_db_path(memory)
    conn = sqlite3.connect(
        path,
        timeout=5.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    if not memory:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            source TEXT NOT NULL,
            entity_id TEXT,
            status TEXT NOT NULL,
            reason TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            metric TEXT NOT NULL,
            observed_value REAL NOT NULL,
            expected_value REAL NOT NULL,
            rule_id TEXT NOT NULL,
            explanation TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            metrics_count INTEGER NOT NULL,
            anomalies_count INTEGER NOT NULL,
            diagnosis_category TEXT,
            evidence_json TEXT NOT NULL DEFAULT '{}',
            symptom TEXT NOT NULL DEFAULT 'other',
            status TEXT NOT NULL DEFAULT 'captured',
            resolution_note TEXT NOT NULL DEFAULT ''
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            pid INTEGER NOT NULL,
            process_name TEXT NOT NULL,
            cpu_percent REAL NOT NULL,
            memory_percent REAL NOT NULL,
            read_bytes_per_sec REAL,
            write_bytes_per_sec REAL,
            network_connection_count INTEGER
        )
    """)
    
    # Indexes for fast querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_timestamp ON anomalies(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_started_at ON incidents(started_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_process_samples_timestamp ON process_samples(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_process_samples_name_timestamp ON process_samples(process_name, timestamp)")

    # Normalize timestamps written by older versions (which could retain local
    # offsets) so text comparisons remain chronological and consistent in UTC.
    schema_version = cursor.execute("PRAGMA user_version").fetchone()[0]
    if schema_version < 1:
        for table, columns in (
            ("metrics", ("timestamp",)),
            ("anomalies", ("timestamp",)),
            ("incidents", ("started_at", "ended_at")),
        ):
            for column in columns:
                rows = cursor.execute(f"SELECT id, {column} FROM {table}").fetchall()
                for row in rows:
                    previous = row[1]
                    if previous is None:
                        continue
                    normalized = serialize_timestamp(parse_timestamp(previous))
                    if normalized != previous:
                        cursor.execute(
                            f"UPDATE {table} SET {column} = ? WHERE id = ?",
                            (normalized, row[0]),
                        )
        cursor.execute("PRAGMA user_version = 1")
        schema_version = 1

    if schema_version < 2:
        incident_columns = {row[1] for row in cursor.execute("PRAGMA table_info(incidents)").fetchall()}
        if "evidence_json" not in incident_columns:
            cursor.execute("ALTER TABLE incidents ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}' ")
        cursor.execute("PRAGMA user_version = 2")
        schema_version = 2

    if schema_version < 3:
        process_columns = {row[1] for row in cursor.execute("PRAGMA table_info(process_samples)").fetchall()}
        for name, sql_type in (
            ("read_bytes_per_sec", "REAL"),
            ("write_bytes_per_sec", "REAL"),
            ("network_connection_count", "INTEGER"),
        ):
            if name not in process_columns:
                cursor.execute(f"ALTER TABLE process_samples ADD COLUMN {name} {sql_type}")
        cursor.execute("PRAGMA user_version = 3")
        schema_version = 3

    if schema_version < 4:
        incident_columns = {row[1] for row in cursor.execute("PRAGMA table_info(incidents)").fetchall()}
        for name, sql_type in (
            ("symptom", "TEXT NOT NULL DEFAULT 'other'"),
            ("status", "TEXT NOT NULL DEFAULT 'captured'"),
            ("resolution_note", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in incident_columns:
                cursor.execute(f"ALTER TABLE incidents ADD COLUMN {name} {sql_type}")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_incidents_status_started ON incidents(status, started_at)")
        cursor.execute("PRAGMA user_version = 4")
    
    conn.commit()

def prune_db(conn: sqlite3.Connection, retention_days: int = 7):
    """Deletes records older than retention_days."""
    cursor = conn.cursor()
    cutoff = serialize_timestamp(datetime.now(timezone.utc) - timedelta(days=retention_days))
    cursor.execute("""
        DELETE FROM metrics 
        WHERE timestamp <= ?
    """, (cutoff,))
    
    cursor.execute("""
        DELETE FROM anomalies 
        WHERE timestamp <= ?
    """, (cutoff,))

    cursor.execute("DELETE FROM process_samples WHERE timestamp <= ?", (cutoff,))
    
    conn.commit()
