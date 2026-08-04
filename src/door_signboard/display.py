"""Generate monochrome images for the Waveshare 3.52-inch display."""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .constants import SignContent
from .scenes import Scene

DISPLAY_WIDTH = 360
DISPLAY_HEIGHT = 240
DISPLAY_SIZE = (DISPLAY_WIDTH, DISPLAY_HEIGHT)

BLACK = 0
WHITE = 255

OUTER_MARGIN = 2
BORDER_BOX = (
    OUTER_MARGIN,
    OUTER_MARGIN,
    DISPLAY_WIDTH - OUTER_MARGIN - 1,
    DISPLAY_HEIGHT - OUTER_MARGIN - 1,
)
CONTENT_BOX = (
    BORDER_BOX[0] + 1,
    BORDER_BOX[1] + 1,
    BORDER_BOX[2],
    BORDER_BOX[3],
)

_FONT_ENV = "DOOR_SIGNBOARD_FONT"
_BOLD_FONT_ENV = "DOOR_SIGNBOARD_BOLD_FONT"
_SYSTEM_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def generate_image(
    scene: Scene,
    content: SignContent | None = None,
    *,
    font_path: str | Path | None = None,
    bold_font_path: str | Path | None = None,
) -> Image.Image:
    """Render a scene as a 360 x 240, one-bit Pillow image."""

    if not isinstance(scene, Scene):
        scene = Scene(scene)

    content = content or SignContent()
    regular_path = _resolve_font(font_path, _FONT_ENV, "DejaVuSans.ttf")
    bold_path = _resolve_font(
        bold_font_path or font_path,
        _BOLD_FONT_ENV,
        "DejaVuSans-Bold.ttf",
    )

    image = Image.new("1", DISPLAY_SIZE, WHITE)
    draw = ImageDraw.Draw(image)

    header_font = ImageFont.truetype(regular_path, 17)
    scene_font = ImageFont.truetype(bold_path, 17)
    title_font = ImageFont.truetype(bold_path, 42)
    footer_font = ImageFont.truetype(regular_path, 15)

    if scene is Scene.DEFAULT:
        name_font = ImageFont.truetype(bold_path, 46)
        apartment_font = ImageFont.truetype(regular_path, 30)
        content_left, content_top, content_right, content_bottom = CONTENT_BOX
        split_y = content_top + (content_bottom - content_top) * 2 // 3
        draw.rectangle(
            (content_left, content_top, content_right - 1, split_y - 1),
            fill=BLACK,
        )
        _draw_centered_in_box(
            draw,
            content.name,
            (content_left, content_top, content_right, split_y),
            name_font,
            WHITE,
        )
        _draw_centered_in_box(
            draw,
            content.apartment_number,
            (content_left, split_y, content_right, content_bottom),
            apartment_font,
            BLACK,
        )
        _draw_border(draw)
        return image

    apartment = f"APT {content.apartment_number}"
    scene_label = scene.value.upper()
    draw.text((14, 11), apartment, font=header_font, fill=BLACK)
    _draw_right_aligned(draw, scene_label, 346, 11, scene_font)
    draw.line((14, 39, 346, 39), fill=BLACK, width=2)

    _draw_centered(draw, scene_label, 53, title_font)
    _draw_fitted_message(
        draw,
        content.message_for(scene),
        bold_path,
        box=(20, 108, 340, 191),
    )

    draw.line((14, 202, 346, 202), fill=BLACK, width=1)
    draw.text((14, 211), content.name, font=footer_font, fill=BLACK)
    _draw_right_aligned(draw, content.phone_number, 346, 211, footer_font)

    _draw_border(draw)
    return image


def _resolve_font(
    explicit_path: str | Path | None,
    environment_variable: str,
    system_filename: str,
) -> str:
    candidates = [
        explicit_path,
        os.environ.get(environment_variable),
        _SYSTEM_FONT_DIR / system_filename,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)

    raise FileNotFoundError(
        f"No usable font found; pass a font path or set {environment_variable}"
    )


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    width = right - left
    draw.text(((DISPLAY_WIDTH - width) // 2, y), text, font=font, fill=BLACK)


def _draw_border(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle(BORDER_BOX, outline=BLACK, width=1)


def _draw_centered_in_box(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    fill: int,
) -> None:
    left, top, right, bottom = box
    text_left, text_top, text_right, text_bottom = draw.textbbox(
        (0, 0), text, font=font
    )
    text_width = text_right - text_left
    text_height = text_bottom - text_top
    position = (
        left + (right - left - text_width) // 2 - text_left,
        top + (bottom - top - text_height) // 2 - text_top,
    )
    draw.text(position, text, font=font, fill=fill)


def _draw_right_aligned(
    draw: ImageDraw.ImageDraw,
    text: str,
    right_edge: int,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text((right_edge - (right - left), y), text, font=font, fill=BLACK)


def _draw_fitted_message(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top

    for font_size in range(27, 15, -1):
        font = ImageFont.truetype(font_path, font_size)
        lines = _wrap_text(draw, text, font, max_width)
        rendered = "\n".join(lines)
        bounds = draw.multiline_textbbox(
            (0, 0), rendered, font=font, spacing=4, align="center"
        )
        text_width = bounds[2] - bounds[0]
        text_height = bounds[3] - bounds[1]
        fits_box = text_width <= max_width and text_height <= max_height
        if len(lines) <= 3 and fits_box:
            position = (
                left + (max_width - text_width) // 2,
                top + (max_height - text_height) // 2,
            )
            draw.multiline_text(
                position,
                rendered,
                font=font,
                fill=BLACK,
                spacing=4,
                align="center",
            )
            return

    raise ValueError("Scene message is too long to fit the display")


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current_line = words[0]
    for word in words[1:]:
        candidate = f"{current_line} {word}"
        bounds = draw.textbbox((0, 0), candidate, font=font)
        if bounds[2] - bounds[0] <= max_width:
            current_line = candidate
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines
