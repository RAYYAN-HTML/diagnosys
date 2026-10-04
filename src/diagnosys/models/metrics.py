from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class MetricStatus(Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    ERROR = "error"

@dataclass
class MetricSample:
    timestamp: datetime
    metric_name: str
    value: Any
    unit: str
    source: str
    status: MetricStatus
    entity_id: Optional[str] = None
    reason: Optional[str] = None

@dataclass
class CPUMetrics:
    utilization_percent: float
    per_core_utilization_percent: List[float]
    frequency_mhz: Optional[float]
    load_average: Optional[List[float]]
    available: bool = True
    reason: Optional[str] = None

@dataclass
class MemoryMetrics:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent_used: float
    swap_percent: Optional[float]
    available: bool = True
    reason: Optional[str] = None

@dataclass
class DiskMetrics:
    total_bytes: int
    free_bytes: int
    percent_used: float
    read_bytes_per_sec: float
    write_bytes_per_sec: float
    busy_percent: Optional[float]
    available: bool = True
    reason: Optional[str] = None

@dataclass
class ProcessInfo:
    pid: int
    name: str
    username: Optional[str]
    cpu_percent: float
    memory_percent: float

@dataclass
class ProcessSnapshot:
    timestamp: datetime
    process_count: int
    top_cpu: List[ProcessInfo]
    top_memory: List[ProcessInfo]
    available: bool = True
    reason: Optional[str] = None

@dataclass
class SystemSnapshot:
    timestamp: datetime
    cpu: CPUMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    uptime_seconds: float
