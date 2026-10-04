import sqlite3
import os
from platformdirs import user_data_dir

APP_NAME = "diagnosys"
APP_AUTHOR = "diagnosys_team"

def get_db_path(memory: bool = False) -> str:
    if memory:
        return ":memory:"
    
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "diagnosys.sqlite")

def get_connection(memory: bool = False) -> sqlite3.Connection:
    path = get_db_path(memory)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
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
            timestamp TIMESTAMP NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            metric TEXT NOT NULL,
            observed_value REAL NOT NULL,
            expected_value REAL NOT NULL,
            rule_id TEXT NOT NULL,
            explanation TEXT NOT NULL
        )
    """)
    
    # Indexes for fast querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anomalies_timestamp ON anomalies(timestamp)")
    
    conn.commit()

def prune_db(conn: sqlite3.Connection, retention_days: int = 7):
    """Deletes records older than retention_days."""
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM metrics 
        WHERE timestamp <= datetime('now', ?)
    """, (f'-{retention_days} days',))
    
    cursor.execute("""
        DELETE FROM anomalies 
        WHERE timestamp <= datetime('now', ?)
    """, (f'-{retention_days} days',))
    
    conn.commit()
