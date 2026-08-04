"""Delivery instruction scene."""

from ..constants import SignContent
from ..display import RenderContext


def render(context: RenderContext, content: SignContent) -> None:
    context.draw_banner("DELIVERY INSTRUCTIONS")

    otp = content.delivery_otp.strip() if content.delivery_otp else None
    message_box = (20, 105, 340, 191) if otp else (20, 52, 340, 191)
    context.draw_fitted_message(content.delivery_message, message_box)
    if otp:
        context.draw_fitted_single_line(f"OTP: {otp}", (20, 55, 340, 102))

    context.draw_footer(content.name, content.apartment_number)
