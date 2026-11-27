from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

TRACK_CHOICES = [("en", "English"), ("de", "German")]
CEFR_CHOICES = [(c, c) for c in ("A1", "A2", "B1", "B2", "C1")]
UI_LANG_CHOICES = [("uz", "O'zbekcha"), ("en", "English"), ("ru", "Русский")]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra):
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """One account for web and Telegram. Email is optional for Telegram-only users."""

    email = models.EmailField(unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=80, blank=True)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)

    active_track = models.CharField(max_length=2, choices=TRACK_CHOICES, default="en")
    cefr_level_en = models.CharField(max_length=2, choices=CEFR_CHOICES, default="A1")
    cefr_level_de = models.CharField(max_length=2, choices=CEFR_CHOICES, default="A1")
    ui_language = models.CharField(max_length=2, choices=UI_LANG_CHOICES, default="uz")

    xp = models.PositiveIntegerField(default=0)
    streak = models.PositiveIntegerField(default=0)
    best_streak = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(null=True, blank=True)
    reminder_time = models.TimeField(null=True, blank=True)
    last_reminder_date = models.DateField(null=True, blank=True)
    notify_classes = models.BooleanField(default=True)  # class deadlines and teacher announcements
    notify_leagues = models.BooleanField(default=True)  # league results and "danger zone" warnings

    # Who brought this user to Yodflip (duel link); set once, when the account is created.
    invited_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="invited")
    # Personal invite code for share cards: t.me/<bot>/<app>?startapp=ref_<code> (created on first use).
    referral_code = models.CharField(max_length=12, unique=True, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self):
        return self.email or self.display_name or f"tg:{self.telegram_id}"

    @property
    def level(self) -> int:
        from gamification.services import level_for_xp

        return level_for_xp(self.xp)

    def cefr_for(self, track: str) -> str:
        return self.cefr_level_de if track == "de" else self.cefr_level_en


class TranslationPreference(models.Model):
    """Translation language + direction chosen before memorization games, per user and track."""

    DIRECTIONS = [("forward", "Word → translation"), ("reverse", "Translation → word")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="translation_prefs")
    track = models.CharField(max_length=2, choices=TRACK_CHOICES)
    preferred_translation_lang = models.CharField(max_length=2, default="uz")
    preferred_direction = models.CharField(max_length=7, choices=DIRECTIONS, default="forward")
    remember_choice = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "track"], name="uniq_translation_pref")]
