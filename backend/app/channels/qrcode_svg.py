from __future__ import annotations

import io

import qrcode
from qrcode.image.svg import SvgPathImage


def qr_svg(data: str, scale: int = 6, dark: str = "#0F1419", light: str = "#F8FAFC") -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=max(3, scale),
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    raw = buf.getvalue().decode("utf-8")
    if "<svg" in raw:
        raw = raw.replace("<svg", f'<svg style="background:{light}"', 1)
    return raw
