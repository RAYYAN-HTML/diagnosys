"""Opt-in game-process session sampling. Does not claim to measure FPS."""
from __future__ import annotations
from dataclasses import dataclass
import time
import psutil

@dataclass(frozen=True)
class GameProcessMetrics:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    thread_count: int | None
    read_bytes_per_sec: float | None
    write_bytes_per_sec: float | None

@dataclass(frozen=True)
class GameSessionSnapshot:
    available: bool
    processes: tuple[GameProcessMetrics, ...] = ()
    reason: str | None = None
    complete: bool = True

class GameSessionCollector:
    """Monitor only process names explicitly supplied by the user."""
    def __init__(self):
        self._previous_io: dict[int, tuple[float, int, int]] = {}

    def collect(self, process_names: list[str]) -> GameSessionSnapshot:
        names = {name.casefold().strip() for name in process_names if name.strip()}
        if not names:
            return GameSessionSnapshot(False, reason="Add game process names to start a focused session.")
        now = time.monotonic()
        results, seen = [], set()
        incomplete = False
        try:
            for process in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "num_threads"]):
                try:
                    info = process.info
                    if (info.get("name") or "").casefold() not in names:
                        continue
                    counters = None
                    try:
                        counters = process.io_counters()
                    except (AttributeError, OSError, psutil.Error, NotImplementedError):
                        pass
                    read_rate = write_rate = None
                    if counters:
                        previous = self._previous_io.get(info["pid"])
                        if previous and now > previous[0]:
                            elapsed = now - previous[0]
                            read_rate = max(0, counters.read_bytes - previous[1]) / elapsed
                            write_rate = max(0, counters.write_bytes - previous[2]) / elapsed
                        self._previous_io[info["pid"]] = (now, counters.read_bytes, counters.write_bytes)
                    results.append(GameProcessMetrics(info["pid"], info.get("name") or "Unknown",
                        float(info.get("cpu_percent") or 0), float(info.get("memory_percent") or 0),
                        info.get("num_threads"), read_rate, write_rate))
                    seen.add(info["pid"])
                except psutil.AccessDenied:
                    incomplete = True
                    continue
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
            self._previous_io = {pid: value for pid, value in self._previous_io.items() if pid in seen}
            if not results:
                if incomplete:
                    return GameSessionSnapshot(False, reason="Game process sampling was incomplete because one or more processes denied access.", complete=False)
                return GameSessionSnapshot(False, reason="None of the configured game processes are running.")
            reason = "Some configured game processes denied access; session detection may be incomplete." if incomplete else None
            return GameSessionSnapshot(
                True, tuple(sorted(results, key=lambda item: item.cpu_percent, reverse=True)),
                reason=reason, complete=not incomplete,
            )
        except (OSError, psutil.Error) as exc:
            return GameSessionSnapshot(False, reason=f"Game process sampling failed: {exc}", complete=False)
