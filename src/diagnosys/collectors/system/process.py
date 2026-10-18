import psutil
import time
from datetime import datetime, timezone

from diagnosys.collectors.base import Collector
from diagnosys.models.metrics import ProcessInfo, ProcessSnapshot

class ProcessCollector(Collector):
    def __init__(self, top_n: int = 5):
        self.top_n = top_n
        self._io_previous: dict[int, tuple[float, int, int]] = {}
        self._network_connections: dict[int, int] = {}
        self._last_network_sample = 0.0

    def collect(self) -> ProcessSnapshot:
        try:
            processes = []
            process_handles = {}
            
            for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    process_info = ProcessInfo(
                            pid=info['pid'],
                            name=info['name'] or f"unknown-{info['pid']}",
                            username=info['username'],
                            cpu_percent=info['cpu_percent'] or 0.0,
                            memory_percent=info['memory_percent'] or 0.0,
                        )
                    processes.append(process_info)
                    process_handles[process_info.pid] = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Sort by CPU
            top_cpu = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)[:self.top_n]
            
            # Sort by Memory
            top_memory = sorted(processes, key=lambda p: p.memory_percent, reverse=True)[:self.top_n]

            now = time.monotonic()
            selected = {item.pid: item for item in (*top_cpu, *top_memory)}
            refresh_connections = now - self._last_network_sample >= 15 or not self._network_connections
            for pid, process_info in selected.items():
                proc = process_handles[pid]
                try:
                    counters = proc.io_counters()
                    previous = self._io_previous.get(pid)
                    if previous:
                        elapsed = now - previous[0]
                        if elapsed > 0:
                            process_info.read_bytes_per_sec = max(0, counters.read_bytes - previous[1]) / elapsed
                            process_info.write_bytes_per_sec = max(0, counters.write_bytes - previous[2]) / elapsed
                    self._io_previous[pid] = (now, counters.read_bytes, counters.write_bytes)
                except (AttributeError, OSError, NotImplementedError, psutil.Error, TypeError):
                    pass
                if refresh_connections or pid not in self._network_connections:
                    try:
                        self._network_connections[pid] = len(proc.net_connections(kind="inet"))
                    except (AttributeError, OSError, NotImplementedError, psutil.Error, TypeError):
                        self._network_connections.pop(pid, None)
                process_info.network_connection_count = self._network_connections.get(pid)

            if refresh_connections:
                self._last_network_sample = now

            live_pids = set(process_handles)
            self._io_previous = {pid: value for pid, value in self._io_previous.items() if pid in live_pids}
            self._network_connections = {pid: value for pid, value in self._network_connections.items() if pid in live_pids}
            
            return ProcessSnapshot(
                timestamp=datetime.now(timezone.utc),
                process_count=len(processes),
                top_cpu=top_cpu,
                top_memory=top_memory
            )
        except Exception as e:
            return ProcessSnapshot(
                timestamp=datetime.now(timezone.utc),
                process_count=0,
                top_cpu=[],
                top_memory=[],
                available=False,
                reason=f"error: {str(e)}"
            )
