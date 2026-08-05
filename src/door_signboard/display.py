"""Common image-generation primitives and scene dispatch."""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .constants import Scene, SignContent

# Canvas dimensions in pixels. The renderer authors everything in landscape.
DISPLAY_WIDTH = 360
DISPLAY_HEIGHT = 240
DISPLAY_SIZE = (DISPLAY_WIDTH, DISPLAY_HEIGHT)

# Pillow mode "1" (1-bit) pixel values: 0 = black, 255 = white.
BLACK = 0
WHITE = 255

# Outer border: a 1px rectangle inset `OUTER_MARGIN` px from every edge.
OUTER_MARGIN = 2
BORDER_BOX = (
    OUTER_MARGIN,
    OUTER_MARGIN,
    DISPLAY_WIDTH - OUTER_MARGIN - 1,
    DISPLAY_HEIGHT - OUTER_MARGIN - 1,
)
# Drawable area just inside the border, where scenes place their content.
CONTENT_BOX = (
    BORDER_BOX[0] + 1,
    BORDER_BOX[1] + 1,
    BORDER_BOX[2],
    BORDER_BOX[3],
)

# Optional overrides for the fonts, useful when the system fonts are elsewhere.
_FONT_ENV = "DOOR_SIGNBOARD_FONT"
_BOLD_FONT_ENV = "DOOR_SIGNBOARD_BOLD_FONT"
_SYSTEM_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

# A rectangle as (left, top, right, bottom) in pixel coordinates.
Box = tuple[int, int, int, int]


class RenderContext:
    """Canvas and reusable drawing operations available to scene renderers."""

    def __init__(self, regular_font_path: str, bold_font_path: str) -> None:
        # Start with a blank white 1-bit canvas that scenes draw onto.
        self.image = Image.new("1", DISPLAY_SIZE, WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self._regular_font_path = regular_font_path
        self._bold_font_path = bold_font_path

    def font(self, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Load the regular or bold font at the given pixel size."""

        path = self._bold_font_path if bold else self._regular_font_path
        return ImageFont.truetype(path, size)

    def draw_banner(self, text: str) -> None:
        """Draw a black title bar with centered white text across the top."""

        # Filled black bar, then white text centered within it.
        self.draw.rectangle((3, 3, 356, 42), fill=BLACK)
        self.draw_centered_in_box(
            text,
            (3, 3, 357, 43),
            self.font(21, bold=True),
            WHITE,
        )

    def draw_footer(self, left_text: str, right_text: str) -> None:
        """Draw a divider line with left- and right-aligned footer text."""

        footer_font = self.font(15)
        # Horizontal rule above the footer row.
        self.draw.line((14, 202, 346, 202), fill=BLACK, width=1)
        # Left text is anchored at the left margin.
        self.draw.text((14, 211), left_text, font=footer_font, fill=BLACK)
        # Right text is right-aligned: measure its width and offset from 346.
        text_left, _, text_right, _ = self.draw.textbbox(
            (0, 0), right_text, font=footer_font
        )
        self.draw.text(
            (346 - (text_right - text_left), 211),
            right_text,
            font=footer_font,
            fill=BLACK,
        )

    def draw_centered_in_box(
        self,
        text: str,
        box: Box,
        font: ImageFont.FreeTypeFont,
        fill: int,
    ) -> None:
        """Draw a single line of text centered within ``box``."""

        left, top, right, bottom = box
        # textbbox reports the glyphs' actual bounds; subtracting text_left/top
        # corrects for fonts whose origin is not at (0, 0).
        text_left, text_top, text_right, text_bottom = self.draw.textbbox(
            (0, 0), text, font=font
        )
        text_width = text_right - text_left
        text_height = text_bottom - text_top
        position = (
            left + (right - left - text_width) // 2 - text_left,
            top + (bottom - top - text_height) // 2 - text_top,
        )
        self.draw.text(position, text, font=font, fill=fill)

    def draw_fitted_message(self, text: str, box: Box) -> None:
        """Word-wrap and center a message, shrinking the font until it fits.

        Tries progressively smaller font sizes and accepts the first that fits
        in at most three lines within ``box``. Raises if nothing fits.
        """

        left, top, right, bottom = box
        max_width = right - left
        max_height = bottom - top

        # Largest to smallest font size; take the first that fits the box.
        for font_size in range(27, 15, -1):
            font = self.font(font_size, bold=True)
            lines = self._wrap_text(text, font, max_width)
            rendered = "\n".join(lines)
            bounds = self.draw.multiline_textbbox(
                (0, 0), rendered, font=font, spacing=4, align="center"
            )
            text_width = bounds[2] - bounds[0]
            text_height = bounds[3] - bounds[1]
            fits_box = text_width <= max_width and text_height <= max_height
            if len(lines) <= 3 and fits_box:
                # Center the wrapped block within the box and draw it.
                self.draw.multiline_text(
                    (
                        left + (max_width - text_width) // 2,
                        top + (max_height - text_height) // 2,
                    ),
                    rendered,
                    font=font,
                    fill=BLACK,
                    spacing=4,
                    align="center",
                )
                return

        raise ValueError("Scene message is too long to fit the display")

    def draw_fitted_single_line(self, text: str, box: Box) -> None:
        """Center one line of text, shrinking the font until it fits the width."""

        max_width = box[2] - box[0]
        for font_size in range(25, 13, -1):
            font = self.font(font_size, bold=True)
            text_left, _, text_right, _ = self.draw.textbbox(
                (0, 0), text, font=font
            )
            if text_right - text_left <= max_width:
                self.draw_centered_in_box(text, box, font, BLACK)
                return

        raise ValueError("Text is too long to fit on one line")

    def draw_border(self) -> None:
        """Draw the 1px rectangle around the whole sign."""

        self.draw.rectangle(BORDER_BOX, outline=BLACK, width=1)

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int,
    ) -> list[str]:
        """Greedily wrap ``text`` into lines no wider than ``max_width``."""

        words = text.split()
        if not words:
            return [""]

        # Greedy wrap: keep adding words to the current line until the next one
        # would overflow, then start a new line.
        lines: list[str] = []
        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}"
            bounds = self.draw.textbbox((0, 0), candidate, font=font)
            if bounds[2] - bounds[0] <= max_width:
                current_line = candidate
            else:
                lines.append(current_line)
                current_line = word
        lines.append(current_line)
        return lines


def generate_image(
    scene: Scene,
    content: SignContent | None = None,
    *,
    font_path: str | Path | None = None,
    bold_font_path: str | Path | None = None,
) -> Image.Image:
    """Render a scene as a 360 x 240, one-bit Pillow image."""

    # Accept a plain string scene (e.g. from JSON) as well as a Scene enum.
    if not isinstance(scene, Scene):
        scene = Scene(scene)

    regular_path = _resolve_font(font_path, _FONT_ENV, "DejaVuSans.ttf")
    bold_path = _resolve_font(
        bold_font_path or font_path,
        _BOLD_FONT_ENV,
        "DejaVuSans-Bold.ttf",
    )
    context = RenderContext(regular_path, bold_path)

    # Import after RenderContext is defined so scene modules can use it without
    # placing scene-specific composition back in this common module.
    from .scenes import RENDERERS

    RENDERERS[scene](context, content or SignContent())
    context.draw_border()
    return context.image


def _resolve_font(
    explicit_path: str | Path | None,
    environment_variable: str,
    system_filename: str,
) -> str:
    """Find a usable font, preferring explicit path, then env var, then system."""

    candidates = [
        explicit_path,
        os.environ.get(environment_variable),
        _SYSTEM_FONT_DIR / system_filename,
    ]
    # Return the first candidate that points to a real file.
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)

    raise FileNotFoundError(
        f"No usable font found; pass a font path or set {environment_variable}"
    )
