"""Scene renderer registry."""

from collections.abc import Callable

from ..constants import Scene, SignContent
from ..display import RenderContext
from .away import render as render_away
from .busy import render as render_busy
from .default import render as render_default
from .delivery import render as render_delivery

SceneRenderer = Callable[[RenderContext, SignContent], None]

RENDERERS: dict[Scene, SceneRenderer] = {
    Scene.DEFAULT: render_default,
    Scene.DELIVERY: render_delivery,
    Scene.AWAY: render_away,
    Scene.BUSY: render_busy,
}
