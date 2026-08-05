"""Scene renderer registry."""

from collections.abc import Callable

from ..constants import Scene, SignContent
from ..display import RenderContext
from .away import render as render_away
from .busy import render as render_busy
from .default import render as render_default
from .delivery import render as render_delivery

# A scene renderer draws its layout onto the shared RenderContext canvas.
SceneRenderer = Callable[[RenderContext, SignContent], None]

# Maps each Scene to the function that draws it. generate_image() looks the
# renderer up here, so adding a scene means adding a module and one entry below.
RENDERERS: dict[Scene, SceneRenderer] = {
    Scene.DEFAULT: render_default,
    Scene.DELIVERY: render_delivery,
    Scene.AWAY: render_away,
    Scene.BUSY: render_busy,
}
