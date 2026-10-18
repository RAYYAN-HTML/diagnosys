import psutil
import time

from diagnosys.collectors.base import Collector
from diagnosys.models.metrics import DiskMetrics

class DiskCollector(Collector):
    def __init__(self):
        self._last_io = None
        self._last_time = None
        
    def collect(self) -> DiskMetrics:
        try:
            # We measure the root or primary partition for simplicity. 
            # In a full implementation, we might aggregate or pick the system drive.
            # Using '/' on Unix and 'C:\\' on Windows. Let's use the first physical partition.
            partitions = psutil.disk_partitions(all=False)
            if not partitions:
                raise ValueError("No disk partitions found")
                
            primary_mount = partitions[0].mountpoint
            usage = psutil.disk_usage(primary_mount)
            
            # Disk IO
            read_bytes_per_sec = 0.0
            write_bytes_per_sec = 0.0
            busy_percent = None
            
            try:
                io_counters = psutil.disk_io_counters()
                current_time = time.time()
                
                if io_counters and self._last_io and self._last_time:
                    dt = current_time - self._last_time
                    if dt > 0:
                        read_bytes_per_sec = (io_counters.read_bytes - self._last_io.read_bytes) / dt
                        write_bytes_per_sec = (io_counters.write_bytes - self._last_io.write_bytes) / dt
                        
                        if hasattr(io_counters, "busy_time") and hasattr(self._last_io, "busy_time"):
                            busy_time_diff = io_counters.busy_time - self._last_io.busy_time
                            busy_percent = (busy_time_diff / (dt * 1000.0)) * 100.0
                            busy_percent = min(100.0, max(0.0, busy_percent))
                            
                self._last_io = io_counters
                self._last_time = current_time
            except Exception:
                pass
                
            return DiskMetrics(
                total_bytes=usage.total,
                free_bytes=usage.free,
                percent_used=usage.percent,
                read_bytes_per_sec=read_bytes_per_sec,
                write_bytes_per_sec=write_bytes_per_sec,
                busy_percent=busy_percent
            )
        except Exception as e:
            return DiskMetrics(
                total_bytes=0,
                free_bytes=0,
                percent_used=0.0,
                read_bytes_per_sec=0.0,
                write_bytes_per_sec=0.0,
                busy_percent=None,
                available=False,
                reason=f"error: {str(e)}"
            )
