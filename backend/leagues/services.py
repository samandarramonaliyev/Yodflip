"""Weekly leagues: joining on the first XP of the week, groups of ≤ 30, zones, the weekly rollover.

All XP reaches the league through `on_xp`, called by gamification.record_activity / add_xp, i.e. only
XP the server itself computed from validated events (games, flashcards, bot quiz, duels, exam
simulations without violations, level bonuses).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from .models import LeagueGroup, LeagueMember, LeagueTier, LeagueWeek, UserLeague, XpFlag

log = logging.getLogger(__name__)
GROUP_SIZE = 30
SMALL_GROUP = 10  # below this the zones are scaled down
M = LeagueMember


# --------------------------------------------------------------------------- time
def tz() -> ZoneInfo:
    return ZoneInfo(settings.LEAGUE_TIMEZONE)


def local(now: datetime | None = None) -> datetime:
    return (now or timezone.now()).astimezone(tz())


def week_start_for(now: datetime | None = None) -> date:
    """Monday of the league week that contains `now` (Monday 00:00 → Sunday 23:59:59, league timezone)."""
    d = local(now).date()
    return d - timedelta(days=d.weekday())


def week_end(start: date) -> datetime:
    """The moment the week is over: next Monday 00:00 in the league timezone."""
    return datetime.combine(start + timedelta(days=7), time.min, tzinfo=tz())


# --------------------------------------------------------------------------- tiers
def tiers() -> list[LeagueTier]:
    return list(LeagueTier.objects.order_by("order"))


def lowest() -> LeagueTier:
    return LeagueTier.objects.order_by("order").first()


def above(t: LeagueTier) -> LeagueTier | None:
    return LeagueTier.objects.filter(order__gt=t.order).order_by("order").first()


def below(t: LeagueTier) -> LeagueTier | None:
    return LeagueTier.objects.filter(order__lt=t.order).order_by("-order").first()


def user_league(user) -> UserLeague:
    ul = UserLeague.objects.select_related("tier").filter(user=user).first()
    if ul:
        return ul
    try:
        with transaction.atomic():
            return UserLeague.objects.create(user=user, tier=lowest())  # new users start in the lowest tier
    except IntegrityError:
        return UserLeague.objects.select_related("tier").get(user=user)


# --------------------------------------------------------------------------- zones
def zones(tier: LeagueTier, n: int, *, is_lowest: bool, is_top: bool) -> tuple[int, int]:
    """(promotion zone, demotion zone) sizes for a group of `n` members.

    Groups of 10+ use the tier's numbers (7 up / 5 down; the top tier gives 3 trophies instead).
    Smaller groups scale both down proportionally: floor(N × n / 10). The demotion zone is then
    clamped so the two zones never overlap and at least one member stays in the middle when the
    group has room for it: demote ≤ n − promote − 1. The lowest tier never demotes.
    """
    promote = tier.promote
    demote = 0 if is_lowest else tier.demote
    if n < SMALL_GROUP:
        promote = promote * n // SMALL_GROUP
        demote = demote * n // SMALL_GROUP
    promote = min(promote, n)
    demote = max(0, min(demote, n - promote - 1))
    return promote, demote


def ranked(group: LeagueGroup) -> list[LeagueMember]:
    """Highest XP first; a tie goes to whoever reached the league first."""
    return list(group.members.select_related("user").order_by("-xp", "joined_at", "id"))


def group_zones(group: LeagueGroup, n: int | None = None) -> tuple[int, int]:
    all_tiers = tiers()
    n = group.size if n is None else n
    return zones(
        group.tier, n, is_lowest=group.tier.order == all_tiers[0].order, is_top=group.tier.order == all_tiers[-1].order
    )


# --------------------------------------------------------------------------- XP
_finalized_before: date | None = None  # per process: weeks before this Monday are known to be finalized


def _finalize_previous(start: date) -> None:
    """Promotions of last week must be applied before anybody joins this week in their (new) tier.
    The hourly cron does this; the first XP of the week does it too if the cron hasn't run yet."""
    global _finalized_before
    if _finalized_before == start:
        return
    if LeagueWeek.objects.filter(start__lt=start, finalized_at__isnull=True).exists():
        finalize_due()
    _finalized_before = start


def on_xp(user, xp: int, now: datetime | None = None) -> None:
    """Add XP to the user's league week; the first XP of the week puts the user into a group."""
    if xp <= 0 or user is None or not user.pk:
        return
    start = week_start_for(now)
    try:
        with transaction.atomic():  # a savepoint: a failure here never breaks the caller's transaction
            _finalize_previous(start)
            if not M.objects.filter(week__start=start, user=user).update(xp=F("xp") + xp):
                _join(user, start, xp)
            check_spike(user, now)
    except Exception:  # the league must never break a game result
        log.exception("League XP for user %s could not be recorded", user.pk)


def _join(user, start: date, xp: int) -> LeagueMember:
    week, _ = LeagueWeek.objects.get_or_create(start=start)
    tier = user_league(user).tier
    group = None
    for _ in range(10):
        group = LeagueGroup.objects.filter(week=week, tier=tier, size__lt=GROUP_SIZE).order_by("number").first()
        if group is None:
            number = (LeagueGroup.objects.filter(week=week, tier=tier).aggregate(m=Max("number"))["m"] or 0) + 1
            try:
                with transaction.atomic():
                    group = LeagueGroup.objects.create(week=week, tier=tier, number=number)
            except IntegrityError:
                continue  # somebody else created it right now
        # Take a seat; fails when the group filled up meanwhile (then try the next group).
        if LeagueGroup.objects.filter(pk=group.pk, size__lt=GROUP_SIZE).update(size=F("size") + 1):
            break
        group = None
    if group is None:
        raise RuntimeError("no league group")
    try:
        with transaction.atomic():
            return M.objects.create(week=week, group=group, user=user, tier=tier, xp=xp)
    except IntegrityError:  # the same user joined in a parallel request: give the seat back
        LeagueGroup.objects.filter(pk=group.pk).update(size=F("size") - 1)
        M.objects.filter(week=week, user=user).update(xp=F("xp") + xp)
        return M.objects.get(week=week, user=user)


def check_spike(user, now: datetime | None = None) -> None:
    """Log a suspicious amount of XP in one day for admin review (once per user and day)."""
    from gamification.models import DailyActivity

    day = timezone.localdate(now or timezone.now())
    act = DailyActivity.objects.filter(user=user, date=day).only("xp").first()
    if act is None or act.xp < settings.LEAGUE_SPIKE_XP:
        return
    _, created = XpFlag.objects.get_or_create(user=user, day=day, reason="daily_spike", defaults={"xp": act.xp})
    if created:
        log.warning("Suspicious XP spike: user %s earned %d XP on %s", user.pk, act.xp, day)


# --------------------------------------------------------------------------- rollover
def finalize_week(week: LeagueWeek, now: datetime | None = None) -> int:
    """Final ranks, promotions / demotions / trophies, exactly once (row lock + finalized_at)."""
    from gamification.services import grant

    now = now or timezone.now()
    if week_end(week.start) > now:
        return 0  # not over yet
    all_tiers = tiers()
    by_order = {t.order: t for t in all_tiers}
    orders = sorted(by_order)
    with transaction.atomic():
        w = LeagueWeek.objects.select_for_update().get(pk=week.pk)
        if w.finalized_at:
            return 0
        moved = 0
        for group in w.groups.select_related("tier"):
            members = ranked(group)
            n = len(members)
            is_top = group.tier.order == orders[-1]
            promote, demote = zones(group.tier, n, is_lowest=group.tier.order == orders[0], is_top=is_top)
            for i, m in enumerate(members):
                new_tier = group.tier
                if i < promote:
                    if is_top:
                        result = M.TROPHY
                    else:
                        result = M.PROMOTED
                        new_tier = by_order[orders[orders.index(group.tier.order) + 1]]
                elif i >= n - demote:
                    result = M.DEMOTED
                    new_tier = by_order[orders[orders.index(group.tier.order) - 1]]
                else:
                    result = M.STAYED
                m.rank, m.result, m.new_tier = i + 1, result, new_tier
                m.save(update_fields=["rank", "result", "new_tier"])
                ul = user_league(m.user)
                ul.tier = new_tier
                if result == M.TROPHY:
                    ul.trophies += 1
                    grant(m.user, "league_trophy")
                ul.save(update_fields=["tier", "trophies"])
                moved += result != M.STAYED
        w.finalized_at = now
        w.save(update_fields=["finalized_at"])
    log.info("League week %s finalized: %d members moved", w.start, moved)
    return moved


def finalize_due(now: datetime | None = None) -> dict:
    """Every week that is over and not finalized yet (normally just last week). Idempotent."""
    now = now or timezone.now()
    current = week_start_for(now)
    done = []
    for w in LeagueWeek.objects.filter(start__lt=current, finalized_at__isnull=True).order_by("start"):
        finalize_week(w, now)
        done.append(w.start.isoformat())
    return {"finalized": done}


# --------------------------------------------------------------------------- views
def tier_dict(t: LeagueTier) -> dict:
    return {
        "code": t.code,
        "order": t.order,
        "emoji": t.emoji,
        "color": t.color,
        "name": {"uz": t.name_uz, "ru": t.name_ru, "en": t.name_en},
    }


def zone_of(index: int, n: int, promote: int, demote: int) -> str:
    if index < promote:
        return "promote"
    if index >= n - demote:
        return "demote"
    return "safe"


def need_to_be_safe(members: list[LeagueMember], index: int, n: int, demote: int) -> int:
    """XP the member at `index` (in the demotion zone) needs to pass the last safe position."""
    if not demote or index < n - demote or n - demote - 1 < 0:
        return 0
    return members[n - demote - 1].xp - members[index].xp + 1


def state(user, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    start = week_start_for(now)
    end = week_end(start)
    ul = user_league(user)
    all_tiers = tiers()
    out = {
        "tiers": [tier_dict(t) for t in all_tiers],
        "tier": tier_dict(ul.tier),
        "trophies": ul.trophies,
        "week": {
            "start": start.isoformat(),
            "ends_at": end.isoformat(),
            "seconds_left": max(0, int((end - now).total_seconds())),
        },
        "joined": False,
        "group": [],
        "zones": None,
        "me": None,
        "last_result": last_result(user),
    }
    m = M.objects.select_related("group__tier").filter(week__start=start, user=user).first()
    if m is None:
        return out
    members = ranked(m.group)
    n = len(members)
    promote, demote = group_zones(m.group, n)
    rows = []
    for i, x in enumerate(members):
        rows.append(
            {
                "rank": i + 1,
                "user_id": x.user_id,
                "name": x.user.display_name or "—",
                "avatar_url": x.user.avatar_url,
                "xp": x.xp,
                "is_me": x.user_id == user.id,
                "zone": zone_of(i, n, promote, demote),
            }
        )
    me_i = next(i for i, x in enumerate(members) if x.user_id == user.id)
    is_top = m.group.tier.order == all_tiers[-1].order
    out.update(
        {
            "joined": True,
            "tier": tier_dict(m.group.tier),
            "group": rows,
            "zones": {"promote": promote, "demote": demote, "size": n, "top_tier": is_top},
            "me": {
                "rank": me_i + 1,
                "xp": members[me_i].xp,
                "zone": rows[me_i]["zone"],
                "need_xp": need_to_be_safe(members, me_i, n, demote),
            },
        }
    )
    return out


def last_result(user) -> dict | None:
    m = (
        M.objects.select_related("week", "tier", "new_tier")
        .filter(user=user, week__finalized_at__isnull=False)
        .order_by("-week__start")
        .first()
    )
    return history_row(m) if m else None


def history_row(m: LeagueMember) -> dict:
    return {
        "week": m.week.start.isoformat(),
        "tier": tier_dict(m.tier),
        "new_tier": tier_dict(m.new_tier) if m.new_tier_id else None,
        "rank": m.rank,
        "xp": m.xp,
        "result": m.result,
    }


def history(user, limit: int = 12) -> list[dict]:
    rows = (
        M.objects.select_related("week", "tier", "new_tier")
        .filter(user=user, week__finalized_at__isnull=False)
        .order_by("-week__start")[:limit]
    )
    return [history_row(m) for m in rows]
