from pathlib import Path
import tempfile
import unittest

from door_signboard import DesiredState, Scene, SignContent
from door_signboard.main import PreviewOrchestrator


class FakeClient:
    def __init__(self) -> None:
        self.applied = []
        self.errors = []

    async def report_applied(self, state) -> None:
        self.applied.append(state)

    async def report_error(self, revision, error) -> None:
        self.errors.append((revision, error))


class PreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_coalesces_to_latest_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.png"
            orchestrator = PreviewOrchestrator(output, debounce_seconds=0.01)
            client = FakeClient()
            orchestrator.client = client
            task = __import__("asyncio").create_task(orchestrator.run())
            await orchestrator.submit(self._state(1, Scene.DEFAULT))
            await orchestrator.submit(self._state(2, Scene.BUSY))

            for _ in range(100):
                if client.applied:
                    break
                await __import__("asyncio").sleep(0.01)

            await orchestrator.stop()
            await task
            self.assertTrue(output.is_file())
            self.assertEqual([state.revision for state in client.applied], [2])

    def _state(self, revision: int, scene: Scene) -> DesiredState:
        return DesiredState(revision, scene, SignContent())


if __name__ == "__main__":
    unittest.main()
