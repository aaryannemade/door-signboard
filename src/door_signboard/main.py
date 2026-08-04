"""Run the Home Assistant-controlled signboard in preview mode."""

import argparse
import asyncio
import logging
from pathlib import Path

from .config import HomeAssistantConfig
from .constants import DesiredState
from .display import generate_image
from .ha_websocket import HomeAssistantWebSocketClient

logger = logging.getLogger(__name__)


class PreviewOrchestrator:
    """Coalesce desired states and render only the latest revision."""

    def __init__(
        self,
        output_path: str | Path,
        *,
        debounce_seconds: float = 0.5,
    ) -> None:
        self.output_path = Path(output_path)
        self.debounce_seconds = debounce_seconds
        self.client: HomeAssistantWebSocketClient | None = None
        self._pending: DesiredState | None = None
        self._changed = asyncio.Event()
        self._stopped = False

    async def submit(self, state: DesiredState) -> None:
        if self._pending is None or state.revision > self._pending.revision:
            self._pending = state
            self._changed.set()

    async def run(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
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
            state = self._pending
            self._pending = None
            if state is not None:
                await self._render(state)

    async def stop(self) -> None:
        self._stopped = True
        self._changed.set()

    async def _render(self, state: DesiredState) -> None:
        try:
            await asyncio.to_thread(self._render_file, state)
            if self.client is not None:
                await self.client.report_applied(state)
            logger.info("Applied revision %s (%s)", state.revision, state.scene.value)
        except Exception as error:
            logger.exception("Failed to render revision %s", state.revision)
            if self.client is not None:
                await self.client.report_error(state.revision, str(error))

    def _render_file(self, state: DesiredState) -> None:
        image = generate_image(state.scene, state.content)
        temporary_path = self.output_path.with_suffix(".tmp")
        image.save(temporary_path, format="PNG")
        temporary_path.replace(self.output_path)


async def run(args) -> None:
    config = HomeAssistantConfig.from_file(args.credentials)
    if args.check_config:
        print(f"Configuration valid for {config.device_id} at {config.url}")
        return

    orchestrator = PreviewOrchestrator(args.output, debounce_seconds=args.debounce)
    client = HomeAssistantWebSocketClient(config, orchestrator.submit)
    orchestrator.client = client
    renderer_task = asyncio.create_task(orchestrator.run())
    try:
        await client.run_forever()
    finally:
        await orchestrator.stop()
        await client.stop()
        await renderer_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", default="credentials.secret")
    parser.add_argument("--output", default="tmp/generated-images/ha-preview.png")
    parser.add_argument("--debounce", type=float, default=0.5)
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
