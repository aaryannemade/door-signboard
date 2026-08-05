"""Physical image output for the Waveshare 3.52-inch e-paper panel."""

from collections.abc import Callable
import hashlib
import threading
from typing import Protocol

from PIL import Image

# The panel is physically portrait (240x360) but content is authored landscape
# (360x240); the vendor buffer handling accepts either orientation.
LANDSCAPE_SIZE = (360, 240)
PORTRAIT_SIZE = (240, 360)


class ImageOutput(Protocol):
    """Interface shared by the hardware driver and the PNG preview output."""

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
    """Drive the physical panel, one full refresh at a time.

    The Waveshare panel is fresh hardware on each refresh: we initialize it,
    push the image, run the full (GC) waveform, then put it back to sleep. A
    lock serializes refreshes, and a hash of the last image lets us skip
    redundant refreshes (which cause visible flashing and wear the panel).

    ``epd_factory``/``cleanup`` are injection hooks used by the tests to run
    without real hardware.
    """

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
        # Hash of the last successfully displayed image, for skip-if-unchanged.
        self._last_digest: bytes | None = None
        # Reentrant lock so only one refresh touches the hardware at a time.
        self._lock = threading.RLock()

    def show(self, image: Image.Image, *, force: bool = False) -> bool:
        """Refresh the panel with ``image``; return True if it actually did.

        Returns False when the image is identical to the last one shown (unless
        ``force``). Raises a DisplayDriverError subclass on hardware failure.
        """

        self._validate_image(image)
        digest = self._digest(image)
        with self._lock:
            # Skip redundant refreshes to avoid flashing and panel wear.
            if not force and digest == self._last_digest:
                return False

            # Build fresh hardware handles for this refresh. `cleanup` powers
            # the panel down and must run regardless of success.
            epd, cleanup = self._create_hardware()
            initialized = False
            # Track the failure to raise (and its underlying cause) so the
            # cleanup in `finally` can still run before we re-raise.
            failure: DisplayDriverError | None = None
            cause: Exception | None = None
            try:
                if epd.init() != 0:
                    failure = DisplayInitializationError(
                        "Waveshare display initialization returned an error"
                    )
                else:
                    initialized = True
                    # Vendor refresh sequence: convert image -> load into RAM ->
                    # select the full (GC) lookup table -> refresh -> sleep.
                    buffer = epd.getbuffer(image)
                    epd.display(buffer)
                    epd.lut_GC()
                    epd.refresh()
                    epd.sleep()
            except TimeoutError as error:
                # The BUSY line never cleared within busy_timeout_seconds.
                failure = DisplayTimeoutError(str(error))
                cause = error
            except DisplayDriverError as error:
                # Already a typed driver error; propagate as-is.
                failure = error
            except Exception as error:
                # Classify unexpected errors by which phase we reached.
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
                # Always attempt to power the panel down. A cleanup failure only
                # becomes the reported error if nothing else already failed.
                try:
                    cleanup()
                except Exception as error:
                    if failure is None:
                        failure = DisplayDriverError(
                            "Failed to clean up the Waveshare display"
                        )
                        cause = error
            if failure is not None:
                # Preserve the original exception as the cause when we have one.
                if cause is not None:
                    raise failure from cause
                raise failure
            # Success: remember this image so an identical one is skipped later.
            self._last_digest = digest
            return True

    def clear(self) -> None:
        # Force a full white refresh, bypassing the skip-if-unchanged check.
        self.show(Image.new("1", LANDSCAPE_SIZE, 1), force=True)

    def close(self) -> None:
        with self._lock:
            if self._cleanup is not None:
                self._cleanup()

    def _create_hardware(self):
        """Return an (epd, cleanup) pair, real or test-injected."""

        if self._epd_factory is not None:
            return self._epd_factory(), self._cleanup or (lambda: None)

        # Import the vendored driver lazily: it touches GPIO/SPI and must not be
        # imported in preview mode or on non-Pi machines.
        from .vendor.waveshare_epd import epd3in52, epdconfig

        return (
            epd3in52.EPD(busy_timeout_seconds=self.busy_timeout_seconds),
            lambda: epdconfig.module_exit(cleanup=True),
        )

    @staticmethod
    def _validate_image(image: Image.Image) -> None:
        """Reject images the panel cannot display before touching hardware."""

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
        """Hash an image's mode, size, and pixels to detect unchanged frames."""

        digest = hashlib.sha256()
        digest.update(f"{image.mode}:{image.width}x{image.height}:".encode())
        digest.update(image.tobytes())
        return digest.digest()
