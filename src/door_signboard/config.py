"""Pi application configuration loaded from an ignored secret file."""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class HomeAssistantConfig:
    url: str
    token: str = field(repr=False)
    device_id: str = "door_signboard"

    @classmethod
    def from_file(
        cls, path: str | Path = "credentials.secret"
    ) -> "HomeAssistantConfig":
        values = _read_secret_file(Path(path))
        required = {"HA-URL", "HA-TOKEN", "DEVICE-ID"}
        missing = sorted(required - values.keys())
        if missing:
            raise ValueError(f"Missing credential keys: {', '.join(missing)}")
        config = cls(
            url=values["HA-URL"].rstrip("/"),
            token=values["HA-TOKEN"],
            device_id=values["DEVICE-ID"],
        )
        config.websocket_url()
        return config

    def websocket_url(self) -> str:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HA-URL must be an absolute http:// or https:// URL")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/api/websocket"
        return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _read_secret_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(
                f"Invalid credentials line {line_number}: expected KEY: value"
            )
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"Invalid credentials line {line_number}")
        values[key] = value
    return values
