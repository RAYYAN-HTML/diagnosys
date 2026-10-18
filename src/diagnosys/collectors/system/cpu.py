import psutil
from typing import List, Optional

from diagnosys.collectors.base import Collector
from diagnosys.models.metrics import CPUMetrics

class CPUCollector(Collector):
    def collect(self) -> CPUMetrics:
        try:
            utilization = psutil.cpu_percent(interval=0.1)
            per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            
            freq = None
            try:
                freq_info = psutil.cpu_freq()
                if freq_info:
                    freq = freq_info.current
            except Exception:
                pass
                
            load_avg = None
            try:
                if hasattr(psutil, "getloadavg"):
                    load_avg = list(psutil.getloadavg())
            except Exception:
                pass
                
            return CPUMetrics(
                utilization_percent=utilization,
                per_core_utilization_percent=per_core,
                frequency_mhz=freq,
                load_average=load_avg
            )
        except Exception as e:
            return CPUMetrics(
                utilization_percent=0.0,
                per_core_utilization_percent=[],
                frequency_mhz=None,
                load_average=None,
                available=False,
                reason=f"error: {str(e)}"
            )
