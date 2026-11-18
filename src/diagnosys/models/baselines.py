from dataclasses import dataclass
from typing import Optional

@dataclass
class MetricBaseline:
    metric_name: str
    median: float
    p95: float
    min_val: float
    max_val: float
    sample_count: int
    window_seconds: int
    available: bool = True
    reason: Optional[str] = None
    mad: float = 0.0
