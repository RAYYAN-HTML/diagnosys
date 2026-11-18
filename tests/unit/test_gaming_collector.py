from types import SimpleNamespace
from unittest.mock import patch

from diagnosys.collectors.system.gaming import GameSessionCollector


class FakeProcess:
    def __init__(self, pid: int, name: str):
        self.info = {
            "pid": pid, "name": name, "cpu_percent": 35.0,
            "memory_percent": 12.5, "num_threads": 24,
        }

    def io_counters(self):
        return SimpleNamespace(read_bytes=4096, write_bytes=2048)


def test_game_collector_samples_only_user_configured_process_names():
    game = FakeProcess(100, "sample-game.exe")
    unrelated = FakeProcess(200, "browser.exe")
    with patch("diagnosys.collectors.system.gaming.psutil.process_iter", return_value=[game, unrelated]):
        snapshot = GameSessionCollector().collect(["SAMPLE-GAME.EXE"])

    assert snapshot.available
    assert len(snapshot.processes) == 1
    process = snapshot.processes[0]
    assert process.pid == 100
    assert process.name == "sample-game.exe"
    assert process.cpu_percent == 35.0
    assert process.memory_percent == 12.5
    assert process.thread_count == 24
    assert process.read_bytes_per_sec is None
    assert process.write_bytes_per_sec is None


def test_game_collector_reports_no_configured_names_without_sampling():
    with patch("diagnosys.collectors.system.gaming.psutil.process_iter") as process_iter:
        snapshot = GameSessionCollector().collect([])

    assert not snapshot.available
    assert "process names" in snapshot.reason
    process_iter.assert_not_called()


def test_game_collector_marks_access_denied_as_incomplete():
    import psutil

    class DeniedProcess:
        @property
        def info(self):
            raise psutil.AccessDenied(pid=300)

    with patch("diagnosys.collectors.system.gaming.psutil.process_iter", return_value=[DeniedProcess()]):
        snapshot = GameSessionCollector().collect(["sample-game.exe"])
    assert not snapshot.available
    assert not snapshot.complete
    assert "denied access" in snapshot.reason
