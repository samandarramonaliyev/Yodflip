"""Weekly leagues: entry, grouping, timezone boundaries, rollover, zones, notifications, anti-abuse."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot

from accounts.models import User
from gamification.models import UserAchievement
from gamification.services import record_activity
from leagues import notify
from leagues import services as S
from leagues.models import LeagueGroup, LeagueMember, LeagueTier, LeagueWeek, UserLeague, XpFlag

pytestmark = pytest.mark.django_db
TASH = ZoneInfo("Asia/Tashkent")
TOKEN = "123456:TEST-token-for-tests"
# A Monday 10:00 in Tashkent.
MON = datetime(2026, 3, 2, 10, 0, tzinfo=TASH)


@pytest.fixture(autouse=True)
def fresh_cache():
    S._finalized_before = None
    yield
    S._finalized_before = None


def tier(code) -> LeagueTier:
    return LeagueTier.objects.get(code=code)


def people(n, start=0, **kw):
    return [
        User.objects.create_user(display_name=f"U{i}", telegram_id=10_000 + i, **kw) for i in range(start, start + n)
    ]


def set_tier(users, code):
    for u in users:
        UserLeague.objects.update_or_create(user=u, defaults={"tier": tier(code)})


def play(users, xps, now=MON):
    for u, xp in zip(users, xps, strict=True):
        S.on_xp(u, xp, now)


@pytest.fixture
def tg(monkeypatch, settings):
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.PUBLIC_URL = "https://yodflip.example.com"
    calls = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return True

    async def no_sleep(s):
        return None

    from telegram_bot import notify as tg_notify

    monkeypatch.setattr(Bot, "__call__", fake_call)
    monkeypatch.setattr(tg_notify, "sleep", no_sleep)
    return calls


# --------------------------------------------------------------------------- tiers, entry, groups
def test_tiers_are_data_driven():
    assert [(t.code, t.emoji, t.promote) for t in S.tiers()] == [
        ("bronze", "🥉", 7),
        ("silver", "🥈", 7),
        ("gold", "🥇", 3),
    ]
    LeagueTier.objects.create(code="diamond", order=3, emoji="💎", name_uz="Olmos", name_ru="Алмаз", name_en="Diamond")
    assert S.above(tier("gold")).code == "diamond"
    assert S.below(tier("bronze")) is None


def test_entry_on_first_weekly_xp_through_record_activity():
    u = people(1)[0]
    record_activity(u, 0, 0, 0)
    assert not LeagueMember.objects.exists()  # no XP, no league
    record_activity(u, 30, 3, 3)
    m = LeagueMember.objects.get(user=u)
    assert m.tier.code == "bronze" and m.xp == 30  # new users start in Bronze
    record_activity(u, 20, 2, 2)
    m.refresh_from_db()
    assert m.xp == 50 and LeagueMember.objects.count() == 1


def test_groups_hold_at_most_30_in_join_order():
    users = people(65)
    play(users, [10] * 65)
    groups = list(LeagueGroup.objects.order_by("number"))
    assert [g.size for g in groups] == [30, 30, 5]
    assert [m.user_id for m in LeagueMember.objects.filter(group=groups[0]).order_by("joined_at", "id")] == [
        u.id for u in users[:30]
    ]
    # tiers never mix
    silver = people(2, start=100)
    set_tier(silver, "silver")
    play(silver, [5, 5])
    assert LeagueGroup.objects.filter(tier__code="silver").get().size == 2


def test_timezone_boundaries_sunday_2359_vs_monday_0000():
    u = people(1)[0]
    sunday_late = datetime(2026, 3, 8, 23, 59, 59, tzinfo=TASH)  # still the week of Monday 2 March
    monday = datetime(2026, 3, 9, 0, 0, tzinfo=TASH)
    assert S.week_start_for(sunday_late).isoformat() == "2026-03-02"
    assert S.week_start_for(monday).isoformat() == "2026-03-09"
    # 18:59:59 UTC on Sunday is already... still Sunday 23:59:59 in Tashkent (UTC+5)
    assert S.week_start_for(sunday_late.astimezone(ZoneInfo("UTC"))).isoformat() == "2026-03-02"
    S.on_xp(u, 10, sunday_late)
    S.on_xp(u, 20, monday)
    rows = {m.week.start.isoformat(): m.xp for m in LeagueMember.objects.select_related("week")}
    assert rows == {"2026-03-02": 10, "2026-03-09": 20}
    assert S.week_end(LeagueWeek.objects.get(start="2026-03-02").start) == monday


# --------------------------------------------------------------------------- zones
@pytest.mark.parametrize(
    ("code", "n", "expected"),
    [
        ("silver", 30, (7, 5)),
        ("silver", 12, (7, 4)),  # zones never overlap, one member stays in the middle
        ("silver", 10, (7, 2)),
        ("silver", 9, (6, 2)),  # < 10: floor(7·9/10)=6, floor(5·9/10)=4 → clamped to 9−6−1=2
        ("silver", 5, (3, 1)),
        ("silver", 2, (1, 0)),
        ("silver", 1, (0, 0)),
        ("bronze", 30, (7, 0)),  # the lowest tier never demotes
        ("bronze", 4, (2, 0)),
        ("gold", 30, (3, 5)),  # top tier: 3 trophies
        ("gold", 5, (1, 2)),
    ],
)
def test_zone_formula(code, n, expected):
    t = tier(code)
    assert S.zones(t, n, is_lowest=code == "bronze", is_top=code == "gold") == expected


# --------------------------------------------------------------------------- rollover
def test_full_group_promotion_and_demotion_once():
    users = people(30)
    set_tier(users, "silver")
    play(users, [300 - i for i in range(30)])  # users[0] is first
    later = MON + timedelta(days=7, hours=1)
    assert S.finalize_due(MON + timedelta(days=6, hours=13))["finalized"] == []  # Sunday 23:00: not over yet
    assert S.finalize_due(later)["finalized"] == ["2026-03-02"]
    tiers = {ul.user_id: ul.tier.code for ul in UserLeague.objects.select_related("tier")}
    assert [tiers[u.id] for u in users[:7]] == ["gold"] * 7
    assert [tiers[u.id] for u in users[7:25]] == ["silver"] * 18
    assert [tiers[u.id] for u in users[25:]] == ["bronze"] * 5
    m = LeagueMember.objects.get(user=users[0])
    assert (m.rank, m.result, m.new_tier.code) == (1, "promoted", "gold")
    # idempotent: a second run (or a parallel cron call) changes nothing
    assert S.finalize_due(later + timedelta(hours=1))["finalized"] == []
    assert S.finalize_week(LeagueWeek.objects.get(), later) == 0
    assert {ul.user_id: ul.tier.code for ul in UserLeague.objects.select_related("tier")} == tiers


def test_ties_go_to_who_joined_first():
    a, b, c = people(3)
    set_tier([a, b, c], "silver")
    play([b, a, c], [50, 50, 10])
    S.finalize_due(MON + timedelta(days=8))
    ranks = {m.user_id: m.rank for m in LeagueMember.objects.all()}
    assert ranks == {b.id: 1, a.id: 2, c.id: 3}


def test_small_group_and_edge_tiers():
    gold = people(5)
    set_tier(gold, "gold")
    play(gold, [50, 40, 30, 20, 10])
    bronze = people(4, start=50)
    play(bronze, [40, 30, 20, 10])  # new users: bronze
    S.finalize_due(MON + timedelta(days=8))
    res = {m.user_id: (m.result, m.new_tier.code) for m in LeagueMember.objects.select_related("new_tier")}
    # gold, 5 people: 1 trophy (top tier keeps its tier), 2 demoted
    assert res[gold[0].id] == ("trophy", "gold")
    assert [res[u.id][0] for u in gold] == ["trophy", "stayed", "stayed", "demoted", "demoted"]
    assert UserLeague.objects.get(user=gold[0]).trophies == 1
    assert UserAchievement.objects.filter(user=gold[0], code="league_trophy").exists()
    # bronze, 4 people: floor(7·4/10)=2 promoted, nobody demoted below bronze
    assert [res[u.id] for u in bronze] == [
        ("promoted", "silver"),
        ("promoted", "silver"),
        ("stayed", "bronze"),
        ("stayed", "bronze"),
    ]


def test_zero_xp_users_keep_their_tier_and_dont_enter():
    active, idle = people(2)
    set_tier([active, idle], "silver")
    S.on_xp(active, 10, MON)
    S.on_xp(idle, 0, MON)
    S.finalize_due(MON + timedelta(days=8))
    assert not LeagueMember.objects.filter(user=idle).exists()
    assert UserLeague.objects.get(user=idle).tier.code == "silver"


def test_first_xp_of_the_new_week_applies_last_weeks_promotion():
    users = people(10)
    play(users, [100 - i for i in range(10)])  # bronze, 10 people → top 7 promoted
    next_monday = MON + timedelta(days=7, minutes=5)
    S.on_xp(users[0], 5, next_monday)  # the cron hasn't run yet
    m = LeagueMember.objects.get(user=users[0], week__start="2026-03-09")
    assert m.tier.code == "silver"


# --------------------------------------------------------------------------- API
def test_league_state_api(client_for):
    users = people(12)
    set_tier(users, "silver")
    play(users, [120 - 10 * i for i in range(12)], now=datetime.now(TASH))
    me = users[11]
    data = client_for(me).get("/api/leagues/").data
    assert data["joined"] and data["tier"]["code"] == "silver"
    assert data["zones"] == {"promote": 7, "demote": 4, "size": 12, "top_tier": False}
    assert data["me"] == {"rank": 12, "xp": 10, "zone": "demote", "need_xp": 41}  # the last safe place has 50 XP
    assert [r["zone"] for r in data["group"]][:8] == ["promote"] * 7 + ["safe"]
    assert data["group"][-1]["is_me"] and set(data["group"][0]) == {
        "rank",
        "user_id",
        "name",
        "avatar_url",
        "xp",
        "is_me",
        "zone",
    }
    assert 0 < data["week"]["seconds_left"] <= 7 * 86400
    newbie = people(1, start=99)[0]
    d2 = client_for(newbie).get("/api/leagues/").data
    assert not d2["joined"] and d2["tier"]["code"] == "bronze"


def test_history_api(client_for):
    u = people(1)[0]
    S.on_xp(u, 40, MON)
    S.finalize_due(MON + timedelta(days=8))
    weeks = client_for(u).get("/api/leagues/history/").data["weeks"]
    assert weeks == [
        {
            "week": "2026-03-02",
            "tier": S.tier_dict(tier("bronze")),
            "new_tier": S.tier_dict(tier("bronze")),
            "rank": 1,
            "xp": 40,
            "result": "stayed",
        }
    ]


# --------------------------------------------------------------------------- notifications
def test_week_results_are_sent_once(tg, monkeypatch):
    monkeypatch.setattr(notify.timezone, "now", lambda: MON + timedelta(days=7, hours=2))
    users = people(3)
    set_tier(users, "silver")
    play(users, [30, 20, 10])  # silver, 3 people: promote floor(2.1)=2, demote min(1, 0)=0
    off = people(1, start=40, notify_leagues=False)[0]
    S.on_xp(off, 5, MON)
    S.finalize_due(MON + timedelta(days=7, hours=1))
    stats = notify.run()
    texts = {c.chat_id: c.text for c in tg}
    assert set(texts) == {u.telegram_id for u in users}
    assert "Oltin" in texts[users[0].telegram_id] and "🎉" in texts[users[0].telegram_id]
    assert "qoldingiz" in texts[users[2].telegram_id]
    assert stats["skipped"]["notifications_off"] == 1
    notify.run()
    assert len(tg) == 3  # idempotent


def test_old_unsent_results_are_dropped(tg):
    u = people(1)[0]
    S.on_xp(u, 10, MON)
    S.finalize_due(MON + timedelta(days=7, hours=1))
    notify.run()  # months later (real clock): the next weeks are running, a stale result is never sent
    assert tg == [] and LeagueMember.objects.get(user=u).result_notified


def test_danger_zone_warning_thursday_to_sunday_once_a_day(tg, monkeypatch):
    users = people(12)
    set_tier(users, "silver")
    thursday = datetime(2026, 3, 5, 12, 0, tzinfo=TASH)
    play(users, [120 - 10 * i for i in range(12)], now=thursday)
    clock = {"now": datetime(2026, 3, 4, 12, 0, tzinfo=TASH)}  # Wednesday: nothing
    monkeypatch.setattr(notify.timezone, "now", lambda: clock["now"])
    monkeypatch.setattr(S.timezone, "now", lambda: clock["now"])
    notify.run()
    assert tg == []
    clock["now"] = datetime(2026, 3, 5, 7, 0, tzinfo=TASH)  # Thursday, too early in the morning
    notify.run()
    assert tg == []
    clock["now"] = thursday
    notify.run()
    assert sorted(c.chat_id for c in tg) == sorted(u.telegram_id for u in users[8:])  # bottom 4
    assert "41 XP" in next(c.text for c in tg if c.chat_id == users[11].telegram_id)
    notify.run()
    clock["now"] = thursday + timedelta(hours=3)
    notify.run()
    assert len(tg) == 4  # at most once per day
    clock["now"] = thursday + timedelta(days=1)
    notify.run()
    assert len(tg) == 8


# --------------------------------------------------------------------------- anti-abuse
def test_replay_cap_reduces_xp_after_five_replays_a_day(api, user, seeded):
    from words.models import Word

    words = list(Word.objects.filter(track="en", level="A1")[:6])
    results = [{"term": w.display, "word_id": w.id, "translation": w.translation_uz, "correct": True} for w in words]
    body = {"game": "speed", "track": "en", "source": "learned", "results": results}
    xps = [api.post("/api/games/results/", body, format="json").data["xp_earned"] for _ in range(7)]
    assert xps[0] > 0 and xps[:5] == [xps[0]] * 5
    assert xps[5] == xps[6] == round(xps[0] * 0.2)
    other = {**body, "results": results[:3]}  # a different set is not a replay
    extra = api.post("/api/games/results/", other, format="json").data["xp_earned"]
    assert extra > 0
    assert LeagueMember.objects.get(user=user).xp == sum(xps) + extra  # the league gets the capped XP


def test_suspicious_spike_is_flagged_once(settings):
    settings.LEAGUE_SPIKE_XP = 500
    u = people(1)[0]
    record_activity(u, 300, 0, 0)
    assert not XpFlag.objects.exists()
    record_activity(u, 300, 0, 0)
    record_activity(u, 300, 0, 0)
    flag = XpFlag.objects.get()
    assert flag.user == u and flag.xp == 600 and flag.reason == "daily_spike"
