"""Away scene."""

from ..constants import SignContent
from ..display import RenderContext


def render(context: RenderContext, content: SignContent) -> None:
    context.draw_banner("IMPORTANT")
    context.draw_fitted_message(content.away_message, (20, 52, 340, 148))
    context.draw_fitted_single_line(
        content.formatted_phone_number(),
        (20, 151, 340, 191),
    )
    context.draw_footer(content.name, content.apartment_number)
