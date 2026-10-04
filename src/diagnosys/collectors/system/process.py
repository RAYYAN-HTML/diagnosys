import psutil
from datetime import datetime, timezone

from diagnosys.collectors.base import Collector
from diagnosys.models.metrics import ProcessInfo, ProcessSnapshot

class ProcessCollector(Collector):
    def __init__(self, top_n: int = 5):
        self.top_n = top_n

    def collect(self) -> ProcessSnapshot:
        try:
            processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    processes.append(
                        ProcessInfo(
                            pid=info['pid'],
                            name=info['name'] or f"unknown-{info['pid']}",
                            username=info['username'],
                            cpu_percent=info['cpu_percent'] or 0.0,
                            memory_percent=info['memory_percent'] or 0.0
                        )
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Sort by CPU
            top_cpu = sorted(processes, key=lambda p: p.cpu_percent, reverse=True)[:self.top_n]
            
            # Sort by Memory
            top_memory = sorted(processes, key=lambda p: p.memory_percent, reverse=True)[:self.top_n]
            
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
