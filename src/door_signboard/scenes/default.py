"""Default resident scene."""

from ..constants import SignContent
from ..display import BLACK, CONTENT_BOX, WHITE, RenderContext


def render(context: RenderContext, content: SignContent) -> None:
    content_left, content_top, content_right, content_bottom = CONTENT_BOX
    split_y = content_top + (content_bottom - content_top) * 2 // 3
    context.draw.rectangle(
        (content_left, content_top, content_right - 1, split_y - 1),
        fill=BLACK,
    )
    context.draw_centered_in_box(
        content.name,
        (content_left, content_top, content_right, split_y),
        context.font(46, bold=True),
        WHITE,
    )
    context.draw_centered_in_box(
        content.apartment_number,
        (content_left, split_y, content_right, content_bottom),
        context.font(30),
        BLACK,
    )
