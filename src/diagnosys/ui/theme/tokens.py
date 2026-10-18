from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Tokens:
    background: str = "#0B100D"
    surface: str = "#111713"
    surface_raised: str = "#151D18"
    surface_hover: str = "#1B2520"
    border: str = "#25322A"
    text: str = "#E8F0EA"
    secondary: str = "#9AA89E"
    muted: str = "#68786E"
    accent: str = "#39D486"
    accent_hover: str = "#53E099"
    accent_dim: str = "#153525"
    warning: str = "#E5B45D"
    error: str = "#E46F70"
    info: str = "#78B7E8"
    shadow: str = "#000000"
    radius_small: int = 10
    radius_medium: int = 14
    radius_large: int = 18

    def qss_values(self) -> dict[str, str]:
        return {
            key: f"{value}px" if key.startswith("radius_") else str(value)
            for key, value in asdict(self).items()
        }


TOKENS = Tokens()
