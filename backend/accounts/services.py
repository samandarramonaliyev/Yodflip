from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def tokens_for(user: User) -> dict:
    from .serializers import UserSerializer

    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": UserSerializer(user).data}


@transaction.atomic
def merge_users(keep: User, drop: User) -> User:
    """Merge `drop` into `keep` (used when linking a Telegram account to a web account).

    Progress, decks, sets and stats move to `keep`. Conflicting word-progress rows keep
    the higher Leitner box.
    """
    from decks.models import Deck, WordSet
    from duels.models import Duel, DuelParticipant
    from gamification.models import DailyActivity, GameSession, UserAchievement
    from words.models import UserWord

    if keep.pk == drop.pk:
        return keep
    for uw in UserWord.objects.filter(user=drop):
        existing = UserWord.objects.filter(user=keep, track=uw.track, term_key=uw.term_key).first()
        if existing:
            existing.box = max(existing.box, uw.box)
            existing.correct_count += uw.correct_count
            existing.miss_count += uw.miss_count
            existing.want_to_learn = existing.want_to_learn or uw.want_to_learn
            existing.save()
            uw.delete()
        else:
            uw.user = keep
            uw.save()
    Deck.objects.filter(owner=drop).update(owner=keep)
    WordSet.objects.filter(owner=drop).update(owner=keep)
    GameSession.objects.filter(user=drop).update(user=keep)
    for act in DailyActivity.objects.filter(user=drop):
        mine, _ = DailyActivity.objects.get_or_create(user=keep, date=act.date)
        mine.xp += act.xp
        mine.correct += act.correct
        mine.attempts += act.attempts
        mine.save()
        act.delete()
    for ua in UserAchievement.objects.filter(user=drop):
        if not UserAchievement.objects.filter(user=keep, code=ua.code).exists():
            ua.user = keep
            ua.save()
        else:
            ua.delete()
    Duel.objects.filter(creator=drop).update(creator=keep)
    Duel.objects.filter(winner=drop).update(winner=keep)
    for p in DuelParticipant.objects.filter(user=drop):
        if not DuelParticipant.objects.filter(duel=p.duel, user=keep).exists():
            p.user = keep
            p.save(update_fields=["user"])
    if hasattr(drop, "quiz_settings") and not hasattr(keep, "quiz_settings"):
        conf = drop.quiz_settings
        conf.user = keep
        conf.save(update_fields=["user"])
    User.objects.filter(invited_by=drop).exclude(pk=keep.pk).update(invited_by=keep)
    keep.xp += drop.xp
    keep.best_streak = max(keep.best_streak, drop.best_streak)
    if drop.telegram_id and not keep.telegram_id:
        tg_id, tg_name, avatar = drop.telegram_id, drop.telegram_username, drop.avatar_url
        drop.telegram_id = None
        drop.save(update_fields=["telegram_id"])
        keep.telegram_id, keep.telegram_username = tg_id, tg_name
        keep.avatar_url = keep.avatar_url or avatar
    keep.save()
    drop.delete()
    return keep
