"""Physical image output for the Waveshare 3.52-inch e-paper panel."""

from collections.abc import Callable
import hashlib
import threading
from typing import Protocol

from PIL import Image

LANDSCAPE_SIZE = (360, 240)
PORTRAIT_SIZE = (240, 360)


class ImageOutput(Protocol):
    def show(self, image: Image.Image, *, force: bool = False) -> bool:
        """Display an image and return whether a physical update occurred."""

    def close(self) -> None:
        """Release output resources."""


class DisplayDriverError(Exception):
    """Base exception for physical display failures."""


class DisplayInitializationError(DisplayDriverError):
    """The display hardware could not be initialized."""


class DisplayTimeoutError(DisplayDriverError):
    """The display BUSY signal did not clear before its deadline."""


class InvalidDisplayImageError(DisplayDriverError):
    """The image cannot be sent to the configured panel."""


class Waveshare3in52DisplayDriver:
    """Serialize full refreshes and manage the Waveshare hardware lifecycle."""

    def __init__(
        self,
        *,
        busy_timeout_seconds: float = 30.0,
        epd_factory: Callable[[], object] | None = None,
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        if busy_timeout_seconds <= 0:
            raise ValueError("busy_timeout_seconds must be greater than zero")
        self.busy_timeout_seconds = busy_timeout_seconds
        self._epd_factory = epd_factory
        self._cleanup = cleanup
        self._last_digest: bytes | None = None
        self._lock = threading.RLock()

    def show(self, image: Image.Image, *, force: bool = False) -> bool:
        self._validate_image(image)
        digest = self._digest(image)
        with self._lock:
            if not force and digest == self._last_digest:
                return False
            epd, cleanup = self._create_hardware()
            initialized = False
            failure: DisplayDriverError | None = None
            cause: Exception | None = None
            try:
                if epd.init() != 0:
                    failure = DisplayInitializationError(
                        "Waveshare display initialization returned an error"
                    )
                else:
                    initialized = True
                    buffer = epd.getbuffer(image)
                    epd.display(buffer)
                    epd.lut_GC()
                    epd.refresh()
                    epd.sleep()
            except TimeoutError as error:
                failure = DisplayTimeoutError(str(error))
                cause = error
            except DisplayDriverError as error:
                failure = error
            except Exception as error:
                cause = error
                if not initialized:
                    failure = DisplayInitializationError(
                        "Failed to initialize the Waveshare display"
                    )
                else:
                    failure = DisplayDriverError(
                        "Failed to refresh the Waveshare display"
                    )
            finally:
                try:
                    cleanup()
                except Exception as error:
                    if failure is None:
                        failure = DisplayDriverError(
                            "Failed to clean up the Waveshare display"
                        )
                        cause = error
            if failure is not None:
                if cause is not None:
                    raise failure from cause
                raise failure
            self._last_digest = digest
            return True

    def clear(self) -> None:
        self.show(Image.new("1", LANDSCAPE_SIZE, 1), force=True)

    def close(self) -> None:
        with self._lock:
            if self._cleanup is not None:
                self._cleanup()

    def _create_hardware(self):
        if self._epd_factory is not None:
            return self._epd_factory(), self._cleanup or (lambda: None)

        from .vendor.waveshare_epd import epd3in52, epdconfig

        return (
            epd3in52.EPD(busy_timeout_seconds=self.busy_timeout_seconds),
            lambda: epdconfig.module_exit(cleanup=True),
        )

    @staticmethod
    def _validate_image(image: Image.Image) -> None:
        if image.mode != "1":
            raise InvalidDisplayImageError(
                f"Expected Pillow mode '1', received {image.mode!r}"
            )
        if image.size not in (LANDSCAPE_SIZE, PORTRAIT_SIZE):
            raise InvalidDisplayImageError(
                "Expected image size 360x240 or 240x360, received "
                f"{image.width}x{image.height}"
            )

    @staticmethod
    def _digest(image: Image.Image) -> bytes:
        digest = hashlib.sha256()
        digest.update(f"{image.mode}:{image.width}x{image.height}:".encode())
        digest.update(image.tobytes())
        return digest.digest()
