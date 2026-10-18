"""Optional NVIDIA telemetry through the vendor's installed command-line tool."""

from __future__ import annotations

import csv
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


class GPUCollector:
    """Read GPU 0 when NVIDIA's ``nvidia-smi`` is installed; never invent values."""

    _QUERY = (
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
        "--id=0",
    )

    def __init__(self) -> None:
        self._executable = shutil.which("nvidia-smi")

    def collect(self) -> GPUMetrics:
        if not self._executable:
            return GPUMetrics(
                available=False,
                reason="NVIDIA GPU telemetry is unavailable (nvidia-smi was not found).",
            )

        try:
            result = subprocess.run(
                [self._executable, *self._QUERY],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if result.returncode != 0:
                detail = result.stderr.strip() or "The GPU query failed."
                return GPUMetrics(available=False, reason=detail)

            row = next(csv.reader([result.stdout.strip()]), [])
            if len(row) < 5:
                return GPUMetrics(available=False, reason="The GPU returned an incomplete telemetry response.")

            def number(value: str) -> float | None:
                try:
                    return float(value.strip())
                except (TypeError, ValueError):
                    return None

            return GPUMetrics(
                name=row[0].strip() or None,
                utilization_percent=number(row[1]),
                memory_used_mib=number(row[2]),
                memory_total_mib=number(row[3]),
                temperature_c=number(row[4]),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return GPUMetrics(available=False, reason=f"GPU telemetry unavailable: {exc}")
