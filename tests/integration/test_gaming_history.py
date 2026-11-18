import sqlite3
from datetime import datetime, timedelta, timezone

from diagnosys.collectors.system.gaming import GameProcessMetrics, GameSessionSnapshot
from diagnosys.storage.database import init_db
from diagnosys.storage.gaming import GamingRepository


def _game_snapshot(cpu: float = 70.0) -> GameSessionSnapshot:
    return GameSessionSnapshot(True, (
        GameProcessMetrics(
            pid=1234, name="example-game.exe", cpu_percent=cpu,
            memory_percent=18.0, thread_count=42,
            read_bytes_per_sec=4096.0, write_bytes_per_sec=2048.0,
        ),
    ))


def test_gaming_repository_tracks_session_lifecycle_and_resource_history():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repository = GamingRepository(conn)
    started = datetime.now(timezone.utc)

    repository.save_snapshot(
        _game_snapshot(), started,
        system_cpu_percent=62.0, gpu_utilization_percent=75.0, gpu_temperature_c=68.0,
    )
    repository.save_snapshot(
        _game_snapshot(85.0), started + timedelta(seconds=10),
        system_cpu_percent=78.0, gpu_utilization_percent=88.0, gpu_temperature_c=72.0,
    )

    sessions = repository.query_sessions()
    assert len(sessions) == 1
    assert sessions[0]["ended_at"] is None
    assert sessions[0]["sample_count"] == 2
    assert sessions[0]["peak_process_cpu_percent"] == 85.0
    assert sessions[0]["average_system_cpu_percent"] == 70.0
    assert sessions[0]["average_gpu_utilization_percent"] == 81.5

    repository.save_snapshot(
        GameSessionSnapshot(False, reason="Game process exited."),
        started + timedelta(seconds=20),
    )
    sessions = repository.query_sessions()
    assert sessions[0]["ended_at"] is not None
    assert len(repository.query_samples(sessions[0]["id"])) == 2
    conn.close()


def test_unavailable_game_sample_closes_existing_session_without_inventing_metrics():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repository = GamingRepository(conn)
    now = datetime.now(timezone.utc)
    repository.save_snapshot(_game_snapshot(), now)
    repository.save_snapshot(GameSessionSnapshot(False, reason="Access denied"), now + timedelta(seconds=2))

    sessions = repository.query_sessions()
    assert len(sessions) == 1
    assert sessions[0]["ended_at"] is not None
    assert sessions[0]["sample_count"] == 1
    assert sessions[0]["average_gpu_utilization_percent"] is None
    conn.close()


def test_incomplete_game_process_snapshot_does_not_end_unseen_session():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    repository = GamingRepository(conn)
    now = datetime.now(timezone.utc)
    repository.save_snapshot(_game_snapshot(), now)
    repository.save_snapshot(
        GameSessionSnapshot(False, reason="Access denied", complete=False),
        now + timedelta(seconds=10),
    )
    sessions = repository.query_sessions()
    assert len(sessions) == 1
    assert sessions[0]["ended_at"] is None
    assert sessions[0]["sample_count"] == 1
    conn.close()
