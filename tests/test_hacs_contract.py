import ast
import importlib.util
import json
from pathlib import Path
import unittest

from door_signboard import Scene
from door_signboard.ha_websocket import FIELD_LIMITS, WS_STATUS, WS_SUBSCRIBE

ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "door_signboard"


def load_component_constants():
    spec = importlib.util.spec_from_file_location(
        "door_signboard_ha_constants", COMPONENT / "const.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HacsContractTests(unittest.TestCase):
    def test_metadata_and_translation_json_are_valid(self) -> None:
        manifest = json.loads((COMPONENT / "manifest.json").read_text())
        hacs = json.loads((ROOT / "hacs.json").read_text())
        json.loads((COMPONENT / "strings.json").read_text())
        json.loads((COMPONENT / "translations" / "en.json").read_text())

        self.assertEqual(manifest["domain"], "door_signboard")
        self.assertEqual(manifest["integration_type"], "device")
        self.assertTrue(manifest["config_flow"])
        self.assertEqual(hacs["name"], "Door Signboard")

    def test_component_files_parse_without_importing_home_assistant(self) -> None:
        for path in COMPONENT.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))

    def test_pi_and_integration_protocol_contract_matches(self) -> None:
        constants = load_component_constants()

        self.assertEqual(constants.SCENES, tuple(scene.value for scene in Scene))
        self.assertEqual(constants.FIELD_LIMITS, FIELD_LIMITS)
        self.assertEqual(constants.WS_SUBSCRIBE, WS_SUBSCRIBE)
        self.assertEqual(constants.WS_STATUS, WS_STATUS)

    def test_brand_icon_exists(self) -> None:
        icon = COMPONENT / "brand" / "icon.png"
        self.assertTrue(icon.is_file())
        self.assertGreater(icon.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
