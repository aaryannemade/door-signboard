from pathlib import Path
import tempfile
import unittest

from door_signboard.config import HomeAssistantConfig


class ConfigTests(unittest.TestCase):
    def test_loads_home_assistant_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.secret"
            path.write_text(
                "HA-URL: https://ha.example.test:8123/base\n"
                "HA-TOKEN: secret-token\n"
                "DEVICE-ID: door_signboard\n"
            )

            config = HomeAssistantConfig.from_file(path)

        self.assertEqual(config.url, "https://ha.example.test:8123/base")
        self.assertEqual(
            config.websocket_url(),
            "wss://ha.example.test:8123/base/api/websocket",
        )
        self.assertNotIn("secret-token", repr(config))

    def test_rejects_invalid_url(self) -> None:
        config = HomeAssistantConfig("ha.local:8123", "token")

        with self.assertRaisesRegex(ValueError, "absolute"):
            config.websocket_url()


if __name__ == "__main__":
    unittest.main()
