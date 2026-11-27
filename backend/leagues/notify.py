"""League bot messages (part of the hourly cron job): week results and the "danger zone" warning.

Both respect the user's notification switch (User.notify_leagues) and a blocked bot. Each message is
claimed with a conditional UPDATE right before it is sent, so repeated cron calls never send twice.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from telegram_bot.notify import Note, send_notes

from . import services as S
from .models import LeagueGroup, LeagueMember

M = LeagueMember
DANGER_DAYS = (3, 4, 5, 6)  # Thursday .. Sunday
DANGER_HOURS = range(10, 22)  # local daytime only: an hourly cron must not wake anybody up
RESULT_MAX_AGE = timedelta(days=6)  # older unsent results are dropped (the next week is running)


def _reachable(user, skipped: Counter) -> bool:
    conf = getattr(user, "quiz_settings", None)
    if not user.telegram_id or not user.is_active:
        skipped["no_telegram"] += 1
    elif not user.notify_leagues:
        skipped["notifications_off"] += 1
    elif conf and conf.bot_blocked:
        skipped["bot_blocked"] += 1
    else:
        return True
    return False


def result_text(m: LeagueMember) -> str:
    from telegram_bot.texts import t

    lang = m.user.ui_language
    tier = (m.new_tier or m.tier).name(lang)
    emoji = (m.new_tier or m.tier).emoji
    key = {M.PROMOTED: "league_up", M.DEMOTED: "league_down", M.TROPHY: "league_trophy"}.get(m.result, "league_stay")
    return t(lang, key, tier=f"{emoji} {tier}", rank=m.rank or 0, xp=m.xp)


def _claim_result(pk: int):
    return lambda: bool(M.objects.filter(pk=pk, result_notified=False).update(result_notified=True))


def _release_result(pk: int):
    return lambda: M.objects.filter(pk=pk).update(result_notified=False)


def result_notes(now=None) -> tuple[list[Note], Counter]:
    from telegram_bot.texts import t

    now = now or timezone.now()
    skipped: Counter = Counter()
    notes = []
    qs = (
        M.objects.filter(result_notified=False, week__finalized_at__isnull=False)
        .exclude(result="")
        .select_related("user__quiz_settings", "tier", "new_tier", "week")
    )
    stale = []
    for m in qs:
        if m.week.finalized_at < now - RESULT_MAX_AGE or not _reachable(m.user, skipped):
            stale.append(m.pk)
            continue
        lang = m.user.ui_language
        notes.append(
            Note(
                m.user_id,
                m.user.telegram_id,
                result_text(m),
                t(lang, "league_open"),
                "/league",
                _claim_result(m.pk),
                _release_result(m.pk),
            )
        )
    M.objects.filter(pk__in=stale).update(result_notified=True)  # never sent later
    return notes, skipped


def _claim_danger(pk: int, day):
    def claim() -> bool:
        free = Q(danger_notified_on__isnull=True) | Q(danger_notified_on__lt=day)
        return bool(M.objects.filter(free, pk=pk).update(danger_notified_on=day))

    return claim


def danger_notes(now=None) -> tuple[list[Note], Counter]:
    """At most once per day, Thursday to Sunday, for members in their group's demotion zone."""
    from telegram_bot.texts import t

    now = now or timezone.now()
    loc = S.local(now)
    skipped: Counter = Counter()
    if loc.weekday() not in DANGER_DAYS or loc.hour not in DANGER_HOURS:
        return [], skipped
    day = loc.date()
    notes = []
    groups = LeagueGroup.objects.filter(week__start=S.week_start_for(now)).select_related("tier")
    for g in groups:
        members = S.ranked(g)
        n = len(members)
        _, demote = S.group_zones(g, n)
        for i in range(n - demote, n):
            m = members[i]
            if m.danger_notified_on == day:
                continue
            u = m.user
            if not _reachable(u, skipped):
                continue
            need = S.need_to_be_safe(members, i, n, demote)
            lang = u.ui_language
            notes.append(
                Note(
                    u.id,
                    u.telegram_id,
                    t(lang, "league_danger", xp=need),
                    t(lang, "league_open"),
                    "/league",
                    _claim_danger(m.pk, day),
                )
            )
    return notes, skipped


def run(budget: float = 8) -> dict:
    """Cron part: finalize finished weeks, then send results and danger-zone warnings."""
    fin = S.finalize_due()
    results, skipped = result_notes()
    danger, skipped2 = danger_notes()
    stats = send_notes(results + danger, budget, dict(skipped + skipped2))
    stats["finalized"] = fin["finalized"]
    return stats
