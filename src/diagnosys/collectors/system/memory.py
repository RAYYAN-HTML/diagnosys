import psutil

from diagnosys.collectors.base import Collector
from diagnosys.models.metrics import MemoryMetrics

class MemoryCollector(Collector):
    def collect(self) -> MemoryMetrics:
        try:
            mem = psutil.virtual_memory()
            
            swap_percent = None
            try:
                swap = psutil.swap_memory()
                swap_percent = swap.percent
            except Exception:
                pass
                
            return MemoryMetrics(
                total_bytes=mem.total,
                used_bytes=mem.used,
                available_bytes=mem.available,
                percent_used=mem.percent,
                swap_percent=swap_percent
            )
        except Exception as e:
            return MemoryMetrics(
                total_bytes=0,
                used_bytes=0,
                available_bytes=0,
                percent_used=0.0,
                swap_percent=None,
                available=False,
                reason=f"error: {str(e)}"
            )
