"""Optional NVIDIA telemetry through the vendor's installed command-line tool."""

from __future__ import annotations

import csv
import math
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GPUMetrics:
    name: str | None = None
    utilization_percent: float | None = None
    memory_used_mib: float | None = None
    memory_total_mib: float | None = None
    temperature_c: float | None = None
    available: bool = True
    reason: str | None = None
    gpu_index: int = 0


class GPUCollector:
    """Read one explicitly selected NVIDIA GPU without inventing missing values."""

    _QUERY = (
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    )

    def __init__(self, gpu_index: int = 0) -> None:
        if isinstance(gpu_index, bool) or not isinstance(gpu_index, int) or gpu_index < 0:
            raise ValueError("gpu_index must be a non-negative integer")
        self.gpu_index = gpu_index
        self._executable = shutil.which("nvidia-smi")

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            parsed = float(value.strip())
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        return parsed if math.isfinite(parsed) and parsed >= 0 else None

    def collect(self) -> GPUMetrics:
        if not self._executable:
            return GPUMetrics(
                available=False,
                reason="NVIDIA GPU telemetry is unavailable (nvidia-smi was not found).",
                gpu_index=self.gpu_index,
            )

        try:
            result = subprocess.run(
                [self._executable, *self._QUERY, f"--id={self.gpu_index}"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or "The GPU query failed."
                return GPUMetrics(available=False, reason=detail, gpu_index=self.gpu_index)

            rows = list(csv.reader(result.stdout.splitlines()))
            if not rows or len(rows[0]) < 5:
                return GPUMetrics(
                    available=False,
                    reason="The GPU returned an incomplete telemetry response.",
                    gpu_index=self.gpu_index,
                )

            row = rows[0]
            name = row[0].strip() or None
            utilization = self._number(row[1])
            memory_used = self._number(row[2])
            memory_total = self._number(row[3])
            temperature = self._number(row[4])
            if name is None and all(value is None for value in (utilization, memory_used, memory_total, temperature)):
                return GPUMetrics(
                    available=False,
                    reason="The selected GPU returned no usable telemetry fields.",
                    gpu_index=self.gpu_index,
                )

            if utilization is not None and utilization > 100:
                utilization = None
            if memory_total is not None and memory_total <= 0:
                memory_total = None
            if memory_used is not None and memory_total is not None and memory_used > memory_total:
                memory_used = None

            return GPUMetrics(
                name=name,
                utilization_percent=utilization,
                memory_used_mib=memory_used,
                memory_total_mib=memory_total,
                temperature_c=temperature,
                gpu_index=self.gpu_index,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return GPUMetrics(
                available=False,
                reason=f"GPU telemetry unavailable: {exc}",
                gpu_index=self.gpu_index,
            )
