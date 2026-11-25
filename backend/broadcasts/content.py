"""Telegram HTML: validation and the {name} / {streak} / {due_words} placeholders."""

from __future__ import annotations

from datetime import timedelta
from html import escape, unescape
from html.parser import HTMLParser

from gamification.services import today
from words.services import due_queryset

MAX_TEXT, MAX_CAPTION = 4096, 1024
TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "blockquote", "tg-spoiler"}
LINKS = ("https://", "http://", "tg://", "mailto:")
DEFAULT_NAME = "do'stim"


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.plain: list[str] = []
        self.error = ""

    def _fail(self, text: str) -> None:
        self.error = self.error or text

    def handle_starttag(self, tag, attrs):
        if tag not in TAGS:
            return self._fail(f"<{tag}> tegi ruxsat etilmagan")
        if tag == "a":
            if not (dict(attrs).get("href") or "").startswith(LINKS):
                return self._fail("Havola <a href=\"https://...\"> ko'rinishida bo'lishi kerak")
        elif attrs and tag not in ("pre", "code", "blockquote"):
            return self._fail(f"<{tag}> tegida atribut bo'lmasligi kerak")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self._fail(f"<{tag}/> tegi ruxsat etilmagan")

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self._fail(f"</{tag}> noto'g'ri yopilgan")

    def handle_data(self, data):
        if "<" in data:
            self._fail('"<" belgisini &lt; deb yozing')
        self.plain.append(data)

    def handle_entityref(self, name):
        self.plain.append(unescape(f"&{name};"))

    def handle_charref(self, name):
        self.plain.append(unescape(f"&#{name};"))

    def handle_comment(self, data):
        self._fail("Izoh (<!-- -->) ruxsat etilmagan")

    handle_decl = handle_pi = unknown_decl = handle_comment


def check_html(text: str, with_photo: bool = False) -> str:
    """Empty when Telegram will accept the text, else the problem (in Uzbek)."""
    parser = _Checker()
    # The longest possible values, so nobody's message goes over the limit.
    parser.feed(text.replace("{name}", "n" * 80).replace("{streak}", "99999").replace("{due_words}", "99999"))
    unfinished = parser.rawdata.startswith("<")  # e.g. a text that ends with "<b"
    parser.close()
    if parser.error:
        return parser.error
    if unfinished:
        return '"<" belgisini &lt; deb yozing'
    if parser.stack:
        return f"<{parser.stack[-1]}> tegi yopilmagan"
    plain = "".join(parser.plain)
    if not plain.strip():
        return "Xabar matni bo'sh"
    limit = MAX_CAPTION if with_photo else MAX_TEXT
    length = len(plain.encode("utf-16-le")) // 2  # Telegram counts UTF-16 units
    return f"Matn juda uzun: {length} / {limit}" if length > limit else ""


def current_streak(user) -> int:
    """The stored streak is only updated by playing: it is over when yesterday was missed."""
    alive = user.last_active_date and user.last_active_date >= today() - timedelta(days=1)
    return user.streak if alive else 0


def render(text: str, user) -> str:
    out = text.replace("{streak}", str(current_streak(user)))
    if "{due_words}" in out:
        out = out.replace("{due_words}", str(due_queryset(user, user.active_track).count()))
    return out.replace("{name}", escape(user.display_name.strip() or DEFAULT_NAME))  # last: names may contain {...}
