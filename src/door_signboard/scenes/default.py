"""Default resident scene."""

from ..constants import SignContent
from ..display import BLACK, CONTENT_BOX, WHITE, RenderContext


def render(context: RenderContext, content: SignContent) -> None:
    # Split the content area into a top 2/3 (name) and bottom 1/3 (apartment).
    content_left, content_top, content_right, content_bottom = CONTENT_BOX
    split_y = content_top + (content_bottom - content_top) * 2 // 3

    # Top band: black background with the resident name in large white text.
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
    # Bottom band: apartment number in black on the white background.
    context.draw_centered_in_box(
        content.apartment_number,
        (content_left, split_y, content_right, content_bottom),
        context.font(30),
        BLACK,
    )
