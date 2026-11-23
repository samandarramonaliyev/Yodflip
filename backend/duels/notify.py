"""Bot messages about duels. Never raises: a failed message must not break the game."""

from __future__ import annotations

import logging

from django.conf import settings

from .models import Duel, DuelParticipant
from .services import duel_path, outcome_of

log = logging.getLogger(__name__)


def _send(user, key: str, button: str, path: str, **kw) -> None:
    if not settings.TELEGRAM_BOT_TOKEN or user is None or not user.telegram_id:
        return
    from telegram_bot.bot import send_to_user
    from telegram_bot.texts import t

    lang = user.ui_language
    try:
        send_to_user(user.telegram_id, t(lang, key, **kw), t(lang, button), path)
    except Exception as exc:  # noqa: BLE001 - blocked bot, network...
        log.info("Duel message to user %s failed: %s", user.pk, exc)


def opponent_finished(duel: Duel) -> None:
    from telegram_bot.texts import t

    creator = duel.participants.select_related("user").get(role=DuelParticipant.CREATOR)
    opp = duel.participants.select_related("user").get(role=DuelParticipant.OPPONENT)
    name = opp.user.display_name if opp.user else t(creator.user.ui_language, "guest")
    _send(
        creator.user,
        f"duel_{outcome_of(creator, opp)}",
        "duel_rematch",
        duel_path(duel.code),
        name=name,
        score=opp.score,
        total=len(duel.words),
        mine=creator.score,
    )


def rematch_ready(duel: Duel) -> None:
    """The rematch creator has played: tell the other player of the previous duel."""
    creator = duel.participants.get(role=DuelParticipant.CREATOR)
    for p in duel.rematch_of.participants.select_related("user").filter(user__isnull=False).exclude(user=duel.creator):
        _send(
            p.user,
            "duel_rematch_ready",
            "duel_open",
            duel_path(duel.code),
            name=duel.creator.display_name,
            score=creator.score,
            total=len(duel.words),
            sec=round(creator.time_ms / 1000),
        )


def expired(duel: Duel) -> None:
    _send(duel.creator, "duel_expired", "duel_new", "/duel")
