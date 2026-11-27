"""Server fallback for share cards (only used when the client export failed).

Small memory use: one RGB canvas of the final size (≈ 6 MB for a story), drawn with plain shapes and
the bundled Nunito font, one render at a time. Emoji are left out (the font has none) and the footer
shows the short link instead of a QR code.
"""

from __future__ import annotations

import io
import math
import re
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parent / "fonts" / "Nunito-Variable.ttf"
SIZES = {"story": (1080, 1920), "square": (1080, 1080)}
THEMES = {
    "violet": {
        "bg": "#6C5CE7",
        "fg": "#FFFFFF",
        "sub": "#E4E0FF",
        "accent": "#FDCB6E",
        "panel": "#7F71EA",
        "shapes": ["#FDCB6E", "#55EFC4", "#FF7675", "#A29BFE"],
    },
    "yellow": {
        "bg": "#FDCB6E",
        "fg": "#2D3436",
        "sub": "#5B5340",
        "accent": "#6C5CE7",
        "panel": "#FEDF9C",
        "shapes": ["#6C5CE7", "#55EFC4", "#FF7675", "#FFEAA7"],
    },
    "dark": {
        "bg": "#1E1B2E",
        "fg": "#FFFFFF",
        "sub": "#C9C6D6",
        "accent": "#FDCB6E",
        "panel": "#2B2840",
        "shapes": ["#6C5CE7", "#FDCB6E", "#55EFC4", "#FF7675"],
    },
}
_ONE_AT_A_TIME = threading.Semaphore(1)
_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⬀-⯿️‍]")


def clean(text: str, limit: int = 60) -> str:
    return " ".join(_EMOJI.sub("", str(text or "")).split())[:limit]


@lru_cache(maxsize=32)
def font(size: int, weight: str = "Black") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:  # noqa: BLE001 - a static font file: use it as it is
        pass
    return f


def _fit(draw: ImageDraw.ImageDraw, text: str, start: int, max_width: int, weight: str = "Black"):
    size = start
    while size > 28:
        f = font(size, weight)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 6
    return font(28, weight)


def _shape(draw, cx, cy, w, h, angle, color):
    """A rotated card (rounded corners are not worth the extra memory of a rotated layer)."""
    a = math.radians(angle)
    pts = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        pts.append((cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)))
    draw.polygon(pts, fill=color)


def render_card(card: dict) -> bytes:
    fmt = card.get("format") if card.get("format") in SIZES else "story"
    th = THEMES.get(card.get("theme")) or THEMES["violet"]
    width, height = SIZES[fmt]
    story = fmt == "story"
    content = card.get("content") or {}
    with _ONE_AT_A_TIME:
        img = Image.new("RGB", (width, height), th["bg"])
        d = ImageDraw.Draw(img)
        _shape(d, 40, 80, 360, 460, -18, th["shapes"][0])
        _shape(d, width + 20, 560 if story else 420, 300, 380, 14, th["shapes"][1])
        _shape(d, 0, height - (560 if story else 300), 260, 330, 10, th["shapes"][2])
        _shape(d, width - 40, height + 20, 340, 420, -12, th["shapes"][3])

        y = 110 if story else 70
        d.text((width / 2, y), "Yodflip", font=font(84 if story else 64), fill=th["fg"], anchor="mt")
        y += 220 if story else 140
        kicker = clean(content.get("kicker"))
        d.text((width / 2, y), kicker, font=_fit(d, kicker, 56, width - 160, "ExtraBold"), fill=th["sub"], anchor="mt")
        y += 120 if story else 90
        main = clean(content.get("main"), 30)
        f = _fit(d, main, 240 if story else 180, width - 120)
        d.text((width / 2, y), main, font=f, fill=th["fg"], anchor="mt")
        y += f.size + (90 if story else 50)

        stats = [s for s in (content.get("stats") or [])[:3] if isinstance(s, dict)]
        if stats:
            gap, box_h = 24, 200 if story else 160
            box_w = (width - 160 - gap * (len(stats) - 1)) // len(stats)
            for i, s in enumerate(stats):
                x0 = 80 + i * (box_w + gap)
                d.rounded_rectangle((x0, y, x0 + box_w, y + box_h), radius=36, fill=th["panel"])
                value, label = clean(s.get("value"), 14), clean(s.get("label"), 20)
                d.text(
                    (x0 + box_w / 2, y + 40), value, font=_fit(d, value, 64, box_w - 30), fill=th["accent"], anchor="mt"
                )
                d.text(
                    (x0 + box_w / 2, y + box_h - 40),
                    label,
                    font=_fit(d, label, 32, box_w - 30, "Bold"),
                    fill=th["sub"],
                    anchor="mb",
                )
            y += box_h + 60

        name = clean(card.get("name"), 40)
        if name:
            d.text((width / 2, y), name, font=_fit(d, name, 52, width - 200, "ExtraBold"), fill=th["fg"], anchor="mt")

        fh = 220 if story else 170
        top = height - fh - (80 if story else 60)
        d.rounded_rectangle((80, top, width - 80, top + fh), radius=44, fill=th["panel"])
        footer = clean(card.get("footer"), 60)
        link = clean(re.sub(r"^https?://|[?#].*$", "", str(card.get("link") or "")), 60)
        d.text((width / 2, top + fh * 0.36), footer, font=_fit(d, footer, 50, width - 220), fill=th["fg"], anchor="mm")
        d.text(
            (width / 2, top + fh * 0.72), link, font=_fit(d, link, 38, width - 220, "Bold"), fill=th["sub"], anchor="mm"
        )

        out = io.BytesIO()
        img.save(out, "PNG", optimize=False)
        del d, img
    return out.getvalue()
