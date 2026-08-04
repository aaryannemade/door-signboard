from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

from door_signboard.display_driver import (
    DisplayDriverError,
    DisplayInitializationError,
    DisplayTimeoutError,
    InvalidDisplayImageError,
    Waveshare3in52DisplayDriver,
)


class FakeEpd:
    def __init__(self, *, fail_at=None, gate=None) -> None:
        self.events = []
        self.fail_at = fail_at
        self.gate = gate

    def _event(self, name, value=None):
        self.events.append(name if value is None else (name, value))
        if self.fail_at == name:
            if name == "refresh_timeout":
                raise TimeoutError("panel stayed busy")
            raise RuntimeError(f"failed at {name}")

    def init(self):
        self._event("init")
        return -1 if self.fail_at == "init_result" else 0

    def getbuffer(self, image):
        self._event("getbuffer", image)
        return [1, 2, 3]

    def display(self, buffer):
        self._event("display", buffer)
        if self.gate is not None:
            self.gate[0].set()
            self.gate[1].wait(1)

    def lut_GC(self):
        self._event("lut_GC")

    def refresh(self):
        if self.fail_at == "refresh_timeout":
            self._event("refresh_timeout")
        self._event("refresh")

    def sleep(self):
        self._event("sleep")


class DisplayDriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("1", (360, 240), 1)

    def test_refreshes_in_vendor_order_and_cleans_up(self) -> None:
        epd = FakeEpd()
        cleanups = []
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: epd, cleanup=lambda: cleanups.append(True)
        )

        self.assertTrue(driver.show(self.image))

        self.assertEqual(
            [event if isinstance(event, str) else event[0] for event in epd.events],
            ["init", "getbuffer", "display", "lut_GC", "refresh", "sleep"],
        )
        self.assertIs(epd.events[1][1], self.image)
        self.assertEqual(epd.events[2][1], [1, 2, 3])
        self.assertEqual(cleanups, [True])

    def test_accepts_native_portrait_image(self) -> None:
        epd = FakeEpd()
        driver = Waveshare3in52DisplayDriver(epd_factory=lambda: epd)

        self.assertTrue(driver.show(Image.new("1", (240, 360), 1)))

    def test_rejects_invalid_image_before_creating_hardware(self) -> None:
        creations = []
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: creations.append(True)
        )

        with self.assertRaisesRegex(InvalidDisplayImageError, "mode"):
            driver.show(Image.new("L", (360, 240), 255))
        with self.assertRaisesRegex(InvalidDisplayImageError, "size"):
            driver.show(Image.new("1", (100, 100), 1))

        self.assertEqual(creations, [])

    def test_skips_duplicate_unless_forced(self) -> None:
        instances = []

        def factory():
            instance = FakeEpd()
            instances.append(instance)
            return instance

        driver = Waveshare3in52DisplayDriver(epd_factory=factory)

        self.assertTrue(driver.show(self.image))
        self.assertFalse(driver.show(self.image.copy()))
        self.assertTrue(driver.show(self.image.copy(), force=True))
        self.assertEqual(len(instances), 2)

    def test_failed_refresh_is_cleaned_up_and_can_be_retried(self) -> None:
        instances = [FakeEpd(fail_at="refresh"), FakeEpd()]
        cleanups = []
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: instances.pop(0),
            cleanup=lambda: cleanups.append(True),
        )

        with self.assertRaisesRegex(DisplayDriverError, "refresh"):
            driver.show(self.image)
        self.assertTrue(driver.show(self.image))
        self.assertEqual(cleanups, [True, True])

    def test_transfer_failure_does_not_mark_image_as_displayed(self) -> None:
        instances = [FakeEpd(fail_at="display"), FakeEpd()]
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: instances.pop(0)
        )

        with self.assertRaises(DisplayDriverError):
            driver.show(self.image)
        self.assertTrue(driver.show(self.image))

    def test_initialization_errors_are_specific(self) -> None:
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: FakeEpd(fail_at="init_result")
        )

        with self.assertRaises(DisplayInitializationError):
            driver.show(self.image)

    def test_busy_timeout_is_translated_and_cleaned_up(self) -> None:
        cleanups = []
        driver = Waveshare3in52DisplayDriver(
            epd_factory=lambda: FakeEpd(fail_at="refresh_timeout"),
            cleanup=lambda: cleanups.append(True),
        )

        with self.assertRaisesRegex(DisplayTimeoutError, "panel stayed busy"):
            driver.show(self.image)
        self.assertEqual(cleanups, [True])

    def test_concurrent_updates_do_not_overlap(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        instances = []

        def factory():
            instance = FakeEpd(gate=(entered, release) if not instances else None)
            instances.append(instance)
            return instance

        driver = Waveshare3in52DisplayDriver(epd_factory=factory)
        second = self.image.copy()
        second.putpixel((0, 0), 0)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_result = executor.submit(driver.show, self.image)
            self.assertTrue(entered.wait(1))
            second_result = executor.submit(driver.show, second)
            time.sleep(0.02)
            self.assertEqual(len(instances), 1)
            release.set()
            self.assertTrue(first_result.result(1))
            self.assertTrue(second_result.result(1))
        self.assertEqual(len(instances), 2)

    def test_vendored_busy_wait_has_a_deadline(self) -> None:
        from door_signboard.vendor.waveshare_epd import epd3in52

        epd = epd3in52.EPD(busy_timeout_seconds=0.001)
        with (
            patch.object(epd3in52.epdconfig, "digital_read", return_value=0),
            patch.object(epd3in52.epdconfig, "delay_ms"),
            self.assertRaisesRegex(TimeoutError, "remained busy"),
        ):
            epd.ReadBusy()

    def test_vendor_cleanup_attempts_every_resource_and_resets_state(self) -> None:
        from door_signboard.vendor.waveshare_epd import epdconfig

        events = []

        class Resource:
            def __init__(self, name, fail=False):
                self.name = name
                self.fail = fail

            def close(self):
                events.append(f"close:{self.name}")
                if self.fail:
                    raise RuntimeError(self.name)

            def off(self):
                events.append(f"off:{self.name}")

        epdconfig._spi = Resource("spi", fail=True)
        epdconfig._rst = Resource("rst")
        epdconfig._dc = Resource("dc")
        epdconfig._power = Resource("power")
        epdconfig._busy = Resource("busy")

        with self.assertRaisesRegex(RuntimeError, "spi"):
            epdconfig.module_exit(cleanup=True)

        self.assertIn("close:busy", events)
        self.assertIsNone(epdconfig._spi)
        self.assertIsNone(epdconfig._busy)


if __name__ == "__main__":
    unittest.main()
