"""Run the Home Assistant-controlled door signboard."""

import argparse
import asyncio
import logging
from pathlib import Path
import time

from PIL import Image

from .config import HomeAssistantConfig
from .constants import DesiredState
from .display import generate_image
from .display_driver import ImageOutput, Waveshare3in52DisplayDriver
from .ha_websocket import HomeAssistantWebSocketClient

logger = logging.getLogger(__name__)


class PreviewImageOutput:
    """Save each rendered image as a PNG on disk (used in preview mode).

    This is the local-development stand-in for the physical panel. It satisfies
    the same ``ImageOutput`` protocol as the hardware driver, so the rest of the
    app does not care which one it is talking to.
    """

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)

    def show(self, image: Image.Image, *, force: bool = False) -> bool:
        # `force` only matters for the hardware driver (which skips unchanged
        # images); writing a PNG is cheap, so we always write and ignore it.
        del force
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file then atomically rename, so a reader never sees a
        # half-written PNG.
        temporary_path = self.output_path.with_suffix(".tmp")
        image.save(temporary_path, format="PNG")
        temporary_path.replace(self.output_path)
        return True

    def close(self) -> None:
        # No resources to release for a file-based output.
        pass


class DisplayOrchestrator:
    """Turn a stream of desired states into physical display refreshes.

    Home Assistant can emit many desired-state events in quick succession (for
    example while a user is typing). This class sits between the WebSocket client
    and the output and does two jobs:

    * Coalescing: if several new states arrive, only the newest revision is ever
      rendered; older ones are dropped.
    * Rate limiting: it waits a short ``debounce`` period for edits to settle,
      and optionally enforces a ``minimum_refresh_interval`` between physical
      refreshes (to limit e-ink panel wear).
    """

    def __init__(
        self,
        output: ImageOutput,
        *,
        debounce_seconds: float = 0.5,
        minimum_refresh_interval: float = 0.0,
    ) -> None:
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds cannot be negative")
        if minimum_refresh_interval < 0:
            raise ValueError("minimum_refresh_interval cannot be negative")
        self.output = output
        self.debounce_seconds = debounce_seconds
        self.minimum_refresh_interval = minimum_refresh_interval
        self.client: HomeAssistantWebSocketClient | None = None
        # Newest desired state waiting to be rendered (None if nothing pending).
        self._pending: DesiredState | None = None
        # Set whenever a newer state arrives; the run loop waits on this.
        self._changed = asyncio.Event()
        self._stopped = False
        # Monotonic timestamp of the last successful physical refresh, used to
        # enforce `minimum_refresh_interval`. None until the first refresh.
        self._last_refresh_at: float | None = None

    async def submit(self, state: DesiredState) -> None:
        """Queue a desired state, keeping only the newest revision.

        Called by the WebSocket client for every accepted event. Older or
        equal revisions are ignored so we never render stale content.
        """

        if self._pending is None or state.revision > self._pending.revision:
            self._pending = state
            self._changed.set()

    async def run(self) -> None:
        """Main loop: wait for changes, settle, respect the interval, render."""

        while not self._stopped:
            # 1. Sleep until a new state is submitted.
            await self._changed.wait()
            self._changed.clear()
            if self._stopped:
                return

            # 2. Debounce: pause briefly so a burst of rapid edits collapses
            #    into a single render. If another change arrives during the
            #    pause, restart the loop and pick up the newer state.
            await asyncio.sleep(self.debounce_seconds)
            if self._stopped:
                return
            if self._changed.is_set():
                continue

            # 3. Rate limit: if we refreshed recently, wait out the remaining
            #    part of `minimum_refresh_interval`. If a newer state arrives
            #    while waiting, restart the loop to render that one instead.
            if self._last_refresh_at is not None:
                remaining = (
                    self.minimum_refresh_interval
                    - (time.monotonic() - self._last_refresh_at)
                )
                if remaining > 0:
                    try:
                        await asyncio.wait_for(self._changed.wait(), timeout=remaining)
                    except TimeoutError:
                        pass  # Interval elapsed with no new state: go render.
                    if self._stopped:
                        return
                    if self._changed.is_set():
                        continue

            # 4. Render the newest pending state.
            state = self._pending
            self._pending = None
            if state is not None:
                await self._render(state)

    async def stop(self) -> None:
        # Signal the loop to exit and wake it if it is currently waiting.
        self._stopped = True
        self._changed.set()

    async def _render(self, state: DesiredState) -> None:
        """Render one state and report success/failure back to Home Assistant."""

        try:
            # Rendering + panel refresh is blocking, so run it off the event
            # loop. `refreshed` is False when the output skipped an unchanged
            # image; only a real refresh resets the rate-limit clock.
            refreshed = await asyncio.to_thread(self._render_output, state)
            if refreshed:
                self._last_refresh_at = time.monotonic()
        except Exception as error:
            logger.exception("Failed to render revision %s", state.revision)
            if self.client is not None:
                # Best-effort error report; a reporting failure must not crash
                # the render loop.
                try:
                    await self.client.report_error(state.revision, str(error))
                except Exception:
                    logger.warning("Failed to report display error", exc_info=True)
            return
        if self.client is not None:
            try:
                await self.client.report_applied(state)
            except Exception:
                logger.warning("Failed to report applied revision", exc_info=True)
        logger.info("Applied revision %s (%s)", state.revision, state.scene.value)

    def _render_output(self, state: DesiredState) -> bool:
        # Runs in a worker thread. Returns True if the output actually updated.
        image = generate_image(state.scene, state.content)
        return self.output.show(image)


class PreviewOrchestrator(DisplayOrchestrator):
    """DisplayOrchestrator preset that writes to a PNG file (used by tests)."""

    def __init__(
        self,
        output_path: str | Path,
        *,
        debounce_seconds: float = 0.5,
    ) -> None:
        super().__init__(
            PreviewImageOutput(output_path),
            debounce_seconds=debounce_seconds,
        )


async def run(args) -> None:
    """Wire up config, output, orchestrator, and WebSocket client, then run."""

    config = HomeAssistantConfig.from_file(args.credentials)
    if args.check_config:
        # `--check-config` just validates credentials and exits.
        print(f"Configuration valid for {config.device_id} at {config.url}")
        return

    # Choose where rendered images go: the real panel on-device, or a PNG file
    # for local development. Both implement the same ImageOutput protocol.
    if args.output_mode == "hardware":
        output: ImageOutput = Waveshare3in52DisplayDriver(
            busy_timeout_seconds=args.busy_timeout
        )
    else:
        output = PreviewImageOutput(args.output)

    # Refresh on every new revision by default. Pass --minimum-refresh-interval
    # to throttle physical refreshes (e.g. to limit e-ink panel wear).
    minimum_refresh_interval = (
        0.0
        if args.minimum_refresh_interval is None
        else args.minimum_refresh_interval
    )
    orchestrator = DisplayOrchestrator(
        output,
        debounce_seconds=args.debounce,
        minimum_refresh_interval=minimum_refresh_interval,
    )

    # The client feeds incoming states into orchestrator.submit; the orchestrator
    # reports applied/error status back through the client.
    client = HomeAssistantWebSocketClient(config, orchestrator.submit)
    orchestrator.client = client

    # Run the render loop as a background task; the WebSocket client runs (and
    # auto-reconnects) in the foreground until stopped.
    renderer_task = asyncio.create_task(orchestrator.run())
    try:
        await client.run_forever()
    finally:
        # Shut everything down in order, ensuring each step runs even if an
        # earlier one raises: stop the loop, close the socket, await the task,
        # then release the display.
        await orchestrator.stop()
        try:
            await client.stop()
        finally:
            try:
                await renderer_task
            finally:
                await asyncio.to_thread(output.close)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", default="credentials.secret")
    parser.add_argument(
        "--output-mode", choices=("preview", "hardware"), default="preview"
    )
    parser.add_argument("--output", default="tmp/generated-images/ha-preview.png")
    parser.add_argument("--debounce", type=float, default=0.5)
    parser.add_argument(
        "--minimum-refresh-interval",
        type=float,
        help=(
            "Minimum seconds between physical display refreshes. "
            "Defaults to 0 (refresh on every new revision)."
        ),
    )
    parser.add_argument("--busy-timeout", type=float, default=30.0)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.info("Stopped Door Signboard")


if __name__ == "__main__":
    main()
