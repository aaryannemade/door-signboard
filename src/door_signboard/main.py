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
    """Atomically save the latest rendered image as a PNG preview."""

    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)

    def show(self, image: Image.Image, *, force: bool = False) -> bool:
        del force
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.output_path.with_suffix(".tmp")
        image.save(temporary_path, format="PNG")
        temporary_path.replace(self.output_path)
        return True

    def close(self) -> None:
        pass


class DisplayOrchestrator:
    """Coalesce desired states and send only the latest revision to an output."""

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
        self._pending: DesiredState | None = None
        self._changed = asyncio.Event()
        self._stopped = False
        self._last_refresh_at: float | None = None

    async def submit(self, state: DesiredState) -> None:
        if self._pending is None or state.revision > self._pending.revision:
            self._pending = state
            self._changed.set()

    async def run(self) -> None:
        while not self._stopped:
            await self._changed.wait()
            self._changed.clear()
            if self._stopped:
                return
            await asyncio.sleep(self.debounce_seconds)
            if self._stopped:
                return
            if self._changed.is_set():
                continue
            if self._last_refresh_at is not None:
                remaining = (
                    self.minimum_refresh_interval
                    - (time.monotonic() - self._last_refresh_at)
                )
                if remaining > 0:
                    try:
                        await asyncio.wait_for(self._changed.wait(), timeout=remaining)
                    except TimeoutError:
                        pass
                    if self._stopped:
                        return
                    if self._changed.is_set():
                        continue
            state = self._pending
            self._pending = None
            if state is not None:
                await self._render(state)

    async def stop(self) -> None:
        self._stopped = True
        self._changed.set()

    async def _render(self, state: DesiredState) -> None:
        try:
            refreshed = await asyncio.to_thread(self._render_output, state)
            if refreshed:
                self._last_refresh_at = time.monotonic()
        except Exception as error:
            logger.exception("Failed to render revision %s", state.revision)
            if self.client is not None:
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
        image = generate_image(state.scene, state.content)
        return self.output.show(image)


class PreviewOrchestrator(DisplayOrchestrator):
    """Backward-compatible preview orchestrator used by existing callers."""

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
    config = HomeAssistantConfig.from_file(args.credentials)
    if args.check_config:
        print(f"Configuration valid for {config.device_id} at {config.url}")
        return

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
    client = HomeAssistantWebSocketClient(config, orchestrator.submit)
    orchestrator.client = client
    renderer_task = asyncio.create_task(orchestrator.run())
    try:
        await client.run_forever()
    finally:
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
