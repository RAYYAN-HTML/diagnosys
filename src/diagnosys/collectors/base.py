from abc import ABC, abstractmethod
from typing import Any

class Collector(ABC):
    """Abstract base class for all collectors."""
    
    @abstractmethod
    def collect(self) -> Any:
        """Collect and return measurements, or handle gracefully."""
        pass
