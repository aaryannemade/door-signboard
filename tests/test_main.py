from pathlib import Path
import asyncio
import tempfile
import unittest
from unittest.mock import patch

from door_signboard import DesiredState, Scene, SignContent
from door_signboard.main import DisplayOrchestrator, PreviewOrchestrator


class FakeClient:
    def __init__(self, *, fail_reports=False) -> None:
        self.applied = []
        self.errors = []
        self.fail_reports = fail_reports

    async def report_applied(self, state) -> None:
        self.applied.append(state)
        if self.fail_reports:
            raise ConnectionError("offline")

    async def report_error(self, revision, error) -> None:
        self.errors.append((revision, error))
        if self.fail_reports:
            raise ConnectionError("offline")


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_coalesces_to_latest_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.png"
            orchestrator = PreviewOrchestrator(output, debounce_seconds=0.01)
            client = FakeClient()
            orchestrator.client = client
            task = asyncio.create_task(orchestrator.run())
            await orchestrator.submit(self._state(1, Scene.DEFAULT))
            await orchestrator.submit(self._state(2, Scene.BUSY))

            for _ in range(100):
                if client.applied:
                    break
                await asyncio.sleep(0.01)

            await orchestrator.stop()
            await task
            self.assertTrue(output.is_file())
            self.assertEqual([state.revision for state in client.applied], [2])

    async def test_output_failure_reports_error_not_applied(self) -> None:
        output = FakeOutput(error=RuntimeError("display failed"))
        orchestrator = DisplayOrchestrator(output, debounce_seconds=0)
        client = FakeClient()
        orchestrator.client = client
        task = asyncio.create_task(orchestrator.run())

        await orchestrator.submit(self._state(7, Scene.BUSY))
        await self._wait_for(lambda: client.errors)
        await orchestrator.stop()
        await task

        self.assertEqual(client.applied, [])
        self.assertEqual(client.errors, [(7, "display failed")])

    async def test_refresh_interval_keeps_only_latest_revision(self) -> None:
        output = FakeOutput()
        orchestrator = DisplayOrchestrator(
            output, debounce_seconds=0, minimum_refresh_interval=0.05
        )
        client = FakeClient()
        orchestrator.client = client
        task = asyncio.create_task(orchestrator.run())

        with patch(
            "door_signboard.main.generate_image",
            side_effect=lambda scene, content: scene,
        ):
            await orchestrator.submit(self._state(1, Scene.DEFAULT))
            await self._wait_for(lambda: len(output.images) == 1)
            await orchestrator.submit(self._state(2, Scene.DELIVERY))
            await orchestrator.submit(self._state(3, Scene.AWAY))
            await self._wait_for(lambda: len(output.images) == 2)

        await orchestrator.stop()
        await task
        self.assertEqual(output.images, [Scene.DEFAULT, Scene.AWAY])
        self.assertEqual([state.revision for state in client.applied], [1, 3])

    async def test_status_failures_do_not_stop_later_outputs(self) -> None:
        output = FakeOutput()
        orchestrator = DisplayOrchestrator(output, debounce_seconds=0)
        client = FakeClient(fail_reports=True)
        orchestrator.client = client
        task = asyncio.create_task(orchestrator.run())

        await orchestrator.submit(self._state(1, Scene.DEFAULT))
        await self._wait_for(lambda: len(output.images) == 1)
        await orchestrator.submit(self._state(2, Scene.BUSY))
        await self._wait_for(lambda: len(output.images) == 2)
        await orchestrator.stop()
        await task

        self.assertEqual([state.revision for state in client.applied], [1, 2])

    async def _wait_for(self, predicate) -> None:
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.01)
        self.fail("Timed out waiting for orchestrator")

    def _state(self, revision: int, scene: Scene) -> DesiredState:
        return DesiredState(revision, scene, SignContent())


class FakeOutput:
    def __init__(self, *, error=None) -> None:
        self.images = []
        self.error = error

    def show(self, image, *, force=False):
        del force
        if self.error is not None:
            raise self.error
        self.images.append(image)
        return True

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
