"""Busy scene."""

from ..constants import SignContent
from ..display import RenderContext


def render(context: RenderContext, content: SignContent) -> None:
    context.draw_banner("IMPORTANT")
    # Single message filling the whole body between banner and footer.
    context.draw_fitted_message(content.busy_message, (20, 52, 340, 191))
    context.draw_footer(content.name, content.apartment_number)
