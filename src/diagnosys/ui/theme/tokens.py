from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class Tokens:
    background: str = "#090D16"
    surface: str = "#101827"
    surface_raised: str = "#151F31"
    surface_hover: str = "#1B2940"
    border: str = "#25334A"
    text: str = "#EDF4FF"
    secondary: str = "#A5B4CC"
    muted: str = "#71819B"
    accent: str = "#63E6BE"
    accent_hover: str = "#8AF0D0"
    accent_dim: str = "#12382F"
    warning: str = "#F4C66A"
    error: str = "#FF7785"
    info: str = "#82B6FF"
    shadow: str = "#02050A"
    radius_small: int = 10
    radius_medium: int = 16
    radius_large: int = 22

    def qss_values(self) -> dict[str, str]:
        return {key: f"{value}px" if key.startswith("radius_") else str(value)
                for key, value in asdict(self).items()}

TOKENS = Tokens()
