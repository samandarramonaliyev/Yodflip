"""Weekly leagues: data-driven tiers, weeks (Monday 00:00 → Sunday 23:59 Asia/Tashkent), groups of ≤ 30."""

from django.conf import settings
from django.db import models


class LeagueTier(models.Model):
    """🥉 Bronza → 🥈 Kumush → 🥇 Oltin (more can be added in the admin, e.g. 💎 Olmos)."""

    code = models.SlugField(max_length=20, unique=True)
    order = models.PositiveSmallIntegerField(unique=True)  # 0 = lowest
    emoji = models.CharField(max_length=8)
    name_uz = models.CharField(max_length=40)
    name_ru = models.CharField(max_length=40)
    name_en = models.CharField(max_length=40)
    color = models.CharField(max_length=7, default="#CD7F32")
    promote = models.PositiveSmallIntegerField(default=7)  # top N move up (on the top tier: N trophies)
    demote = models.PositiveSmallIntegerField(default=5)  # bottom N move down (never on the lowest tier)

    class Meta:
        ordering = ("order",)

    def __str__(self):
        return f"{self.emoji} {self.name_uz}"

    def name(self, lang: str) -> str:
        return getattr(self, f"name_{lang}", "") or self.name_uz


class LeagueWeek(models.Model):
    start = models.DateField(unique=True)  # Monday (league timezone)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-start",)

    def __str__(self):
        return f"{self.start} {'✓' if self.finalized_at else '…'}"


class LeagueGroup(models.Model):
    week = models.ForeignKey(LeagueWeek, on_delete=models.CASCADE, related_name="groups")
    tier = models.ForeignKey(LeagueTier, on_delete=models.PROTECT, related_name="groups")
    number = models.PositiveIntegerField()
    size = models.PositiveSmallIntegerField(default=0)  # members, kept by conditional UPDATEs

    class Meta:
        constraints = [models.UniqueConstraint(fields=["week", "tier", "number"], name="uniq_league_group")]
        ordering = ("week", "tier__order", "number")

    def __str__(self):
        return f"{self.week.start} {self.tier.code} #{self.number} ({self.size})"


class LeagueMember(models.Model):
    PROMOTED, DEMOTED, STAYED, TROPHY = "promoted", "demoted", "stayed", "trophy"
    RESULTS = [(r, r) for r in (PROMOTED, DEMOTED, STAYED, TROPHY)]

    week = models.ForeignKey(LeagueWeek, on_delete=models.CASCADE, related_name="members")
    group = models.ForeignKey(LeagueGroup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="league_entries")
    tier = models.ForeignKey(LeagueTier, on_delete=models.PROTECT, related_name="+")
    xp = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)
    rank = models.PositiveSmallIntegerField(null=True, blank=True)  # final, set at the rollover
    result = models.CharField(max_length=10, choices=RESULTS, blank=True)
    new_tier = models.ForeignKey(LeagueTier, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    result_notified = models.BooleanField(default=False)
    danger_notified_on = models.DateField(null=True, blank=True)  # local date of the last "danger zone" message

    class Meta:
        constraints = [models.UniqueConstraint(fields=["week", "user"], name="uniq_league_member")]
        indexes = [models.Index(fields=["group", "-xp"], name="league_member_rank")]

    def __str__(self):
        return f"{self.user} {self.week.start} {self.xp} XP"


class UserLeague(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="league")
    tier = models.ForeignKey(LeagueTier, on_delete=models.PROTECT, related_name="+")
    trophies = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.user} {self.tier.code}"


class XpFlag(models.Model):
    """A suspicious XP spike for admin review (logged once per user, day and reason)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xp_flags")
    day = models.DateField()
    xp = models.PositiveIntegerField()
    reason = models.CharField(max_length=40)
    reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "day", "reason"], name="uniq_xp_flag")]
        ordering = ("-created_at",)
