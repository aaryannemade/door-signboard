"""Pi application configuration loaded from an ignored secret file."""

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class HomeAssistantConfig:
    """Connection details for Home Assistant, loaded from the secret file."""

    url: str
    # repr=False keeps the long-lived token out of logs and error tracebacks.
    token: str = field(repr=False)
    device_id: str = "door_signboard"

    @classmethod
    def from_file(
        cls, path: str | Path = "credentials.secret"
    ) -> "HomeAssistantConfig":
        """Build a config from a ``KEY: value`` credentials file."""

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
        # Validate the URL up front so misconfiguration fails at startup rather
        # than on the first connection attempt.
        config.websocket_url()
        return config

    def websocket_url(self) -> str:
        """Derive the WebSocket API URL from the configured base HTTP URL.

        http -> ws and https -> wss, with ``/api/websocket`` appended.
        """

        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HA-URL must be an absolute http:// or https:// URL")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/api/websocket"
        # Rebuild with the new scheme/path and no query or fragment.
        return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def _read_secret_file(path: Path) -> dict[str, str]:
    """Parse a simple ``KEY: value`` file into an upper-cased-key dict.

    Blank lines and ``#`` comments are ignored. Keys are normalized to
    upper case so ``ha-url`` and ``HA-URL`` are treated the same.
    """

    if not path.is_file():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Split on the first ":" only, so values may themselves contain colons
        # (e.g. a URL like http://host:8123).
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
