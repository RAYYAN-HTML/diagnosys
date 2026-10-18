"""Models describing runtime feature availability."""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    available: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
