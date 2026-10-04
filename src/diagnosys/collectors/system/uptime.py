import psutil
import time

from diagnosys.collectors.base import Collector

class UptimeCollector(Collector):
    def collect(self) -> float:
        try:
            boot_time = psutil.boot_time()
            return time.time() - boot_time
        except Exception:
            return 0.0
