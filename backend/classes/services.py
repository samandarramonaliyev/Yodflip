"""Classes: permissions, limits, joining, assignment progress (from the existing learned / found data)."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from gamification.models import DailyActivity, GameSession
from gamification.services import today, week_start
from words.leitner import MAX_BOX
from words.models import UserLevelWord, UserWord, Word, term_key

from .models import Assignment, Classroom, CoTeacher, Membership, Organization, new_join_code, new_teacher_code

LESSON = 20  # same lesson size as the word list study mode (words/study.py)
M = Membership


# --------------------------------------------------------------------------- access
def teacher_ids(cls: Classroom) -> set[int]:
    ids = {cls.owner_id, *cls.co_teachers.values_list("user_id", flat=True)}
    if cls.org_id:
        ids |= set(cls.org.admins.values_list("id", flat=True))
    return ids


def can_teach(user, cls: Classroom) -> bool:
    return user.is_authenticated and user.id in teacher_ids(cls)


def is_owner(user, cls: Classroom) -> bool:
    return cls.owner_id == user.id or (cls.org_id is not None and cls.org.admins.filter(pk=user.pk).exists())


def membership(user, cls: Classroom) -> Membership | None:
    return M.objects.filter(classroom=cls, user=user).first()


def is_student(user, cls: Classroom) -> bool:
    return M.objects.filter(classroom=cls, user=user, status=M.ACTIVE).exists()


def get_class(pk) -> Classroom:
    cls = Classroom.objects.select_related("owner", "org").filter(pk=pk).first()
    if cls is None:
        raise NotFound("class_not_found")
    return cls


def teaching(user, pk) -> Classroom:
    """The class, when `user` may see its teacher data (owner, co-teacher, org admin). Else 404:
    other people must not even learn that the class exists."""
    cls = get_class(pk)
    if not can_teach(user, cls):
        raise NotFound("class_not_found")
    return cls


def owning(user, pk) -> Classroom:
    cls = teaching(user, pk)
    if not is_owner(user, cls):
        raise PermissionDenied("owner_only")
    return cls


def visible_classes(user):
    """Classes the user teaches (incl. as an org admin) or studies in."""
    teach = Q(owner=user) | Q(co_teachers__user=user) | Q(org__admins=user)
    study = Q(memberships__user=user, memberships__status__in=[M.ACTIVE, M.PENDING])
    return Classroom.objects.filter(teach | study).distinct().select_related("owner", "org")


# --------------------------------------------------------------------------- limits
def limits(plan: str, org: Organization | None = None) -> dict:
    base = dict(settings.CLASS_LIMITS.get(plan) or settings.CLASS_LIMITS["free"])
    if org is not None:
        base = dict(settings.CLASS_LIMITS.get(org.plan) or base)
        if org.max_classes:
            base["classes"] = org.max_classes
        if org.max_students:
            base["students"] = org.max_students
    return base


def class_limits(cls: Classroom) -> dict:
    return limits(cls.plan, cls.org)


def check_can_create(user, org: Organization | None) -> None:
    if org is not None:
        if not (org.teachers.filter(pk=user.pk).exists() or org.admins.filter(pk=user.pk).exists()):
            raise PermissionDenied("not_org_teacher")
        used = org.classes.filter(archived=False).count()
        limit = limits(org.plan, org)["classes"]
    else:
        used = Classroom.objects.filter(owner=user, org__isnull=True, archived=False).count()
        limit = limits("free")["classes"]
    if used >= limit:
        raise ValidationError({"detail": "class_limit", "limit": limit})


def active_count(cls: Classroom) -> int:
    return M.objects.filter(classroom=cls, status=M.ACTIVE).count()


# --------------------------------------------------------------------------- create / join
def _unique(field: str, make) -> str:
    for _ in range(20):
        code = make()
        if not Classroom.objects.filter(**{field: code}).exists():
            return code
    raise RuntimeError("no free code")


def create_class(user, data: dict) -> Classroom:
    org = None
    if data.get("org"):
        org = Organization.objects.filter(pk=data["org"]).first()
        if org is None:
            raise ValidationError({"org": "not_found"})
    check_can_create(user, org)
    return Classroom.objects.create(
        owner=user,
        org=org,
        plan=org.plan if org else "free",
        name=data["name"],
        track=data["track"],
        level=data.get("level") or "",
        description=data.get("description") or "",
        color=data.get("color") or "#6C5CE7",
        approval_required=bool(data.get("approval_required")),
        join_code=_unique("join_code", new_join_code),
        teacher_code=_unique("teacher_code", new_teacher_code),
    )


def regenerate_code(cls: Classroom) -> Classroom:
    cls.join_code = _unique("join_code", new_join_code)
    cls.save(update_fields=["join_code"])
    return cls


def regenerate_teacher_code(cls: Classroom) -> Classroom:
    cls.teacher_code = _unique("teacher_code", new_teacher_code)
    cls.save(update_fields=["teacher_code"])
    return cls


def by_code(code: str) -> Classroom:
    cls = Classroom.objects.select_related("owner", "org").filter(join_code=(code or "").strip().upper()).first()
    if cls is None or cls.archived:
        raise NotFound("class_not_found")
    return cls


def join(user, code: str) -> Membership:
    """Join (or ask to join) a class. Idempotent: joining twice returns the same membership."""
    cls = by_code(code)
    if can_teach(user, cls):
        raise ValidationError({"detail": "is_teacher"})
    with transaction.atomic():
        m = M.objects.select_for_update().filter(classroom=cls, user=user).first()
        if m and m.status in (M.ACTIVE, M.PENDING):
            return m
        if m and m.status == M.REMOVED:
            raise PermissionDenied("removed_from_class")
        status = M.PENDING if cls.approval_required else M.ACTIVE
        if status == M.ACTIVE and active_count(cls) >= class_limits(cls)["students"]:
            raise ValidationError({"detail": "class_full", "limit": class_limits(cls)["students"]})
        if m:  # left earlier, comes back
            m.status = status
            m.save(update_fields=["status", "updated_at"])
            return m
        try:
            with transaction.atomic():
                return M.objects.create(classroom=cls, user=user, status=status)
        except IntegrityError:
            return M.objects.get(classroom=cls, user=user)


def approve(cls: Classroom, user_id: int) -> Membership:
    with transaction.atomic():
        m = M.objects.select_for_update().filter(classroom=cls, user_id=user_id, status=M.PENDING).first()
        if m is None:
            raise NotFound("not_pending")
        if active_count(cls) >= class_limits(cls)["students"]:
            raise ValidationError({"detail": "class_full", "limit": class_limits(cls)["students"]})
        m.status = M.ACTIVE
        m.save(update_fields=["status", "updated_at"])
    return m


def remove(cls: Classroom, user_id: int) -> None:
    n = M.objects.filter(classroom=cls, user_id=user_id, status__in=[M.ACTIVE, M.PENDING]).update(
        status=M.REMOVED, updated_at=timezone.now()
    )
    if not n:
        raise NotFound("not_a_member")


def leave(user, cls: Classroom) -> None:
    M.objects.filter(classroom=cls, user=user, status__in=[M.ACTIVE, M.PENDING]).update(
        status=M.LEFT, updated_at=timezone.now()
    )


def join_as_teacher(user, code: str) -> Classroom:
    cls = Classroom.objects.filter(teacher_code=(code or "").strip().upper(), archived=False).first()
    if cls is None:
        raise NotFound("class_not_found")
    if not can_teach(user, cls):
        CoTeacher.objects.get_or_create(classroom=cls, user=user)
        # A teacher is not a student of the same class.
        M.objects.filter(classroom=cls, user=user, status__in=[M.ACTIVE, M.PENDING]).update(status=M.LEFT)
    return cls


def student_ids(cls: Classroom) -> list[int]:
    return list(M.objects.filter(classroom=cls, status=M.ACTIVE).values_list("user_id", flat=True))


def announcement_recipients(qs, ref: str):
    """Broadcast audience "class": the active students of that class who allow class messages."""
    if not str(ref).isdigit():
        return qs.none()
    ids = M.objects.filter(classroom_id=int(ref), status=M.ACTIVE).values_list("user_id", flat=True)
    return qs.filter(pk__in=ids, notify_classes=True)


# --------------------------------------------------------------------------- links
def links(cls: Classroom) -> dict:
    base = settings.PUBLIC_URL.rstrip("/")
    bot, app = settings.TELEGRAM_BOT_USERNAME, settings.TELEGRAM_APP_SHORT_NAME
    if bot and app:
        tg = f"https://t.me/{bot}/{app}?startapp=class_{cls.join_code}"
    elif bot:
        tg = f"https://t.me/{bot}?start=class_{cls.join_code}"
    else:
        tg = ""
    return {"web": f"{base}/join/{cls.join_code}", "telegram": tg, "teacher": f"{base}/teach/{cls.teacher_code}"}


def code_from_param(param: str | None) -> str:
    """'class_ABC234' → 'ABC234' ('' for anything else)."""
    p = (param or "").strip()
    code = p[6:] if p.startswith("class_") else ""
    return code.upper() if code.isascii() and code.isalnum() and len(code) == 6 else ""


# --------------------------------------------------------------------------- assignments
def _level_words(track: str, level: str):
    return Word.objects.filter(track=track, level=level).order_by("pack__order", "id")


def assignment_words(kind: str, track: str, *, level="", lesson_from=None, lesson_to=None, exam_slug="", topics=()):
    """The ordered built-in word ids of a level / exam pack assignment."""
    if kind == Assignment.LEVEL:
        ids = list(_level_words(track, level).values_list("id", flat=True))
        if lesson_from or lesson_to:
            lo = max(1, lesson_from or 1)
            hi = max(lo, lesson_to or lo)
            ids = ids[(lo - 1) * LESSON : hi * LESSON]
        return ids
    if kind == Assignment.EXAM:
        from exams.services import get_pack, pack_words

        pack = get_pack(exam_slug, track)
        seen, ids = set(), []
        for wid in pack_words(pack, ",".join(topics)).values_list("id", flat=True):
            if wid not in seen:
                seen.add(wid)
                ids.append(wid)
        return ids
    return []


def create_assignment(cls: Classroom, user, d: dict) -> Assignment:
    from decks.models import Deck

    kind = d["kind"]
    a = Assignment(
        classroom=cls,
        created_by=user,
        title=d.get("title") or "",
        kind=kind,
        target_kind=d.get("target_kind") or Assignment.LEARN,
        target_value=d.get("target_value") or 80,
        starts_on=d.get("starts_on") or today(),
        due_at=d["due_at"],
    )
    if a.target_kind == Assignment.LEARN and not 1 <= a.target_value <= 100:
        raise ValidationError({"target_value": "1-100"})
    if a.due_at <= timezone.make_aware(datetime.combine(a.starts_on, time.min)):
        raise ValidationError({"due_at": "before_start"})
    if kind == Assignment.DECK:
        deck = Deck.objects.filter(pk=d.get("deck")).first()
        if deck is None or (deck.owner_id != user.id and not deck.is_public):
            raise ValidationError({"deck": "not_available"})
        if deck.track != cls.track:
            raise ValidationError({"deck": "track_mismatch"})
        a.deck = deck
    elif kind == Assignment.LEVEL:
        if d.get("level") not in ("A1", "A2", "B1", "B2", "C1"):
            raise ValidationError({"level": "invalid"})
        a.level, a.lesson_from, a.lesson_to = d["level"], d.get("lesson_from"), d.get("lesson_to")
    elif kind == Assignment.EXAM:
        a.exam_slug, a.topics = d.get("exam_slug") or "", list(d.get("topics") or [])
    else:
        raise ValidationError({"kind": "invalid"})
    if kind != Assignment.DECK:
        try:
            a.word_ids = assignment_words(
                kind,
                cls.track,
                level=a.level,
                lesson_from=a.lesson_from,
                lesson_to=a.lesson_to,
                exam_slug=a.exam_slug,
                topics=a.topics,
            )
        except Exception as exc:  # unknown pack
            raise ValidationError({"exam_slug": "invalid"}) from exc
        if not a.word_ids:
            raise ValidationError({"detail": "no_words"})
    if not a.title:
        a.title = default_title(a)
    a.save()
    return a


def default_title(a: Assignment) -> str:
    if a.kind == Assignment.LEVEL:
        lessons = ""
        if a.lesson_from:
            upto = f"–{a.lesson_to}" if a.lesson_to and a.lesson_to != a.lesson_from else ""
            lessons = f" · {a.lesson_from}{upto}"
        return f"{a.level}{lessons}"
    if a.kind == Assignment.EXAM:
        return a.exam_slug
    return a.deck.name if a.deck else "Deck"


def deck_terms(a: Assignment) -> list[str]:
    from games.sources import item_from_card

    if not a.deck_id:
        return []
    return [term_key(item_from_card(c)["term"]) for c in a.deck.cards.select_related("deck")]


def learned_sets(a: Assignment, user_ids: list[int]) -> tuple[dict[int, set], int]:
    """({user: the assignment's words this user has learned}, number of words).

    Built-in words: found (level progress) or Learned (box 5). Each word is a set member, so a word
    found in a level AND learned in a deck counts once. Deck cards: Learned (box 5) by normalised term,
    the same identity the lists use.
    """
    track = a.classroom.track
    out: dict[int, set] = defaultdict(set)
    if not user_ids:
        return out, len(a.word_ids) if a.kind != Assignment.DECK else len(set(deck_terms(a)))
    if a.kind == Assignment.DECK:
        keys = set(deck_terms(a))
        rows = UserWord.objects.filter(user_id__in=user_ids, track=track, box__gte=MAX_BOX, term_key__in=keys)
        for uid, key in rows.values_list("user_id", "term_key"):
            out[uid].add(key)
        return out, len(keys)
    ids = set(a.word_ids)
    found = UserLevelWord.objects.filter(user_id__in=user_ids, word_id__in=ids, found_at__isnull=False)
    for uid, wid in found.values_list("user_id", "word_id"):
        out[uid].add(wid)
    key_to_id = {term_key(w.display): w.id for w in Word.objects.filter(id__in=ids).only("id", "word", "article")}
    boxed = UserWord.objects.filter(user_id__in=user_ids, track=track, box__gte=MAX_BOX).filter(
        Q(word_id__in=ids) | Q(term_key__in=list(key_to_id))
    )
    for uid, wid, key in boxed.values_list("user_id", "word_id", "term_key"):
        wid = wid if wid in ids else key_to_id.get(key)
        if wid:
            out[uid].add(wid)
    return out, len(ids)


def _start_dt(a: Assignment):
    return timezone.make_aware(datetime.combine(a.starts_on, time.min))


def plays(a: Assignment, user_ids: list[int]) -> dict[int, int]:
    rows = (
        GameSession.objects.filter(assignment=a, user_id__in=user_ids, created_at__gte=_start_dt(a))
        .values("user_id")
        .annotate(n=Count("id"))
    )
    return {r["user_id"]: r["n"] for r in rows}


def progress(a: Assignment, user_ids: list[int], now=None) -> dict[int, dict]:
    """Per student: {done, total, percent, plays, status: done | overdue | pending | upcoming}."""
    now = now or timezone.now()
    learned, total = learned_sets(a, user_ids)
    played = plays(a, user_ids)
    out = {}
    for uid in user_ids:
        done = len(learned.get(uid, ()))
        percent = round(100 * done / total) if total else 0
        n = played.get(uid, 0)
        if a.target_kind == Assignment.PLAYS:
            complete = n >= a.target_value
            percent_target = min(100, round(100 * n / max(1, a.target_value)))
        else:
            complete = total > 0 and done * 100 >= a.target_value * total
            percent_target = min(100, round(100 * percent / max(1, a.target_value)))
        if complete:
            status = "done"
        elif now > a.due_at:
            status = "overdue"
        elif a.starts_on > timezone.localdate(now):
            status = "upcoming"
        else:
            status = "pending"
        out[uid] = {
            "done": done,
            "total": total,
            "percent": percent,
            "plays": n,
            "target_percent": percent_target,
            "status": status,
        }
    return out


def assignment_dict(a: Assignment) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "kind": a.kind,
        "level": a.level,
        "lesson_from": a.lesson_from,
        "lesson_to": a.lesson_to,
        "exam_slug": a.exam_slug,
        "topics": a.topics,
        "deck": a.deck_id,
        "deck_name": a.deck.name if a.deck_id else "",
        "word_count": len(a.word_ids) if a.kind != Assignment.DECK else len(set(deck_terms(a))),
        "target_kind": a.target_kind,
        "target_value": a.target_value,
        "starts_on": a.starts_on.isoformat(),
        "due_at": a.due_at.isoformat(),
        "start": start_target(a),
    }


def start_target(a: Assignment) -> dict:
    """What "Boshlash" opens: the game source with exactly the assignment's words."""
    if a.kind == Assignment.DECK:
        return {"source": "deck", "id": a.deck_id, "assignment": a.id}
    return {"source": "assignment", "id": a.id, "assignment": a.id}


def assignment_for_player(user, pk) -> Assignment:
    """An assignment the user may play: active student or teacher of its class."""
    a = Assignment.objects.select_related("classroom", "deck").filter(pk=pk).first()
    if a is None or not (is_student(user, a.classroom) or can_teach(user, a.classroom)):
        raise NotFound("assignment_not_found")
    return a


def deck_assigned_to(user, deck) -> bool:
    """Students may play a (private) deck their teacher assigned to their class."""
    return Assignment.objects.filter(
        deck=deck, classroom__memberships__user=user, classroom__memberships__status=M.ACTIVE
    ).exists()


def assignment_items(user, a: Assignment, track: str) -> list[dict]:
    """Game items for source=assignment: the words not learned yet (all of them once everything is learned)."""
    import random

    from games.sources import item_from_word

    if a.kind == Assignment.DECK or track != a.classroom.track:
        return []
    learned = learned_sets(a, [user.id])[0].get(user.id, set())
    words = list(Word.objects.filter(id__in=a.word_ids))
    todo = [w for w in words if w.id not in learned] or words
    random.shuffle(todo)
    return [item_from_word(w) for w in todo]


# --------------------------------------------------------------------------- dashboards
def current_streak(u: User) -> int:
    return u.streak if u.last_active_date and u.last_active_date >= today() - timedelta(days=1) else 0


def person(u: User) -> dict:
    """What teachers and classmates may see: never emails, phone numbers or Telegram ids."""
    return {"id": u.id, "name": u.display_name or "—", "avatar_url": u.avatar_url}


def _week_start_dt():
    return timezone.make_aware(datetime.combine(week_start(), time.min))


def _by_user(qs, field="n") -> dict[int, int]:
    return {r["user_id"]: r[field] or 0 for r in qs}


def student_rows(cls: Classroom, assignments: list[Assignment] | None = None) -> list[dict]:
    ms = list(M.objects.filter(classroom=cls, status__in=[M.ACTIVE, M.PENDING]).select_related("user"))
    ids = [m.user_id for m in ms if m.status == M.ACTIVE]
    track = cls.track
    found = UserLevelWord.objects.filter(user_id__in=ids, track=track, found_at__isnull=False)
    found_total = _by_user(found.values("user_id").annotate(n=Count("id")))
    found_week = _by_user(found.filter(found_at__gte=_week_start_dt()).values("user_id").annotate(n=Count("id")))
    extra = _by_user(
        UserWord.objects.filter(user_id__in=ids, track=track, box__gte=MAX_BOX, word__isnull=True)
        .values("user_id")
        .annotate(n=Count("id"))
    )
    acts = DailyActivity.objects.filter(user_id__in=ids)
    month = (
        acts.filter(date__gte=today() - timedelta(days=29))
        .values("user_id")
        .annotate(c=Sum("correct"), a=Sum("attempts"))
    )
    accuracy = {r["user_id"]: round(100 * (r["c"] or 0) / r["a"]) if r["a"] else None for r in month}
    weekly = _by_user(acts.filter(date__gte=week_start()).values("user_id").annotate(n=Sum("xp")))
    assignments = assignments if assignments is not None else list(cls.assignments.select_related("deck"))
    status = {a.id: progress(a, ids) for a in assignments}
    rows = []
    for m in ms:
        u = m.user
        rows.append(
            {
                **person(u),
                "membership": m.status,
                "joined_at": m.joined_at.isoformat(),
                "last_active": u.last_active_date.isoformat() if u.last_active_date else None,
                "words_week": found_week.get(u.id, 0),
                "words_total": found_total.get(u.id, 0) + extra.get(u.id, 0),
                "accuracy": accuracy.get(u.id),
                "streak": current_streak(u),
                "weekly_xp": weekly.get(u.id, 0),
                "assignments": {
                    str(a.id): status[a.id][u.id] for a in assignments if m.status == M.ACTIVE and u.id in status[a.id]
                },
            }
        )
    return rows


def overview(cls: Classroom, rows: list[dict], assignments: list[Assignment]) -> dict:
    active = [r for r in rows if r["membership"] == M.ACTIVE]
    ws = week_start().isoformat()
    cells = [s for r in active for s in r["assignments"].values()]
    percents = [s["target_percent"] for s in cells]
    return {
        "students": len(active),
        "pending": len(rows) - len(active),
        "active_week": sum(1 for r in active if r["last_active"] and r["last_active"] >= ws),
        "avg_progress": round(sum(percents) / len(percents)) if percents else 0,
        "completion": round(100 * sum(1 for s in cells if s["status"] == "done") / len(cells)) if cells else 0,
        "assignments": len(assignments),
    }


def class_dict(cls: Classroom, user, *, teacher: bool) -> dict:
    out = {
        "id": cls.id,
        "name": cls.name,
        "track": cls.track,
        "level": cls.level,
        "description": cls.description,
        "color": cls.color,
        "archived": cls.archived,
        "teacher": person(cls.owner),
        "org": {"id": cls.org_id, "name": cls.org.name} if cls.org_id else None,
        "role": "teacher" if teacher else "student",
        "students": active_count(cls),
    }
    if teacher:
        lim = class_limits(cls)
        out.update(
            {
                "join_code": cls.join_code,
                "links": links(cls),
                "approval_required": cls.approval_required,
                "plan": cls.plan,
                "limits": lim,
                "is_owner": is_owner(user, cls),
                "co_teachers": [person(c.user) for c in cls.co_teachers.select_related("user")],
            }
        )
        if out["is_owner"]:
            out["links"]["teacher"] = links(cls)["teacher"]
        else:
            out["links"].pop("teacher", None)
    else:
        m = membership(user, cls)
        out["membership"] = m.status if m else None
        out["links"] = {}
    return out


def student_detail(cls: Classroom, user_id: int) -> dict:
    """Only class-related numbers of one student of this class."""
    m = M.objects.select_related("user").filter(classroom=cls, user_id=user_id, status=M.ACTIVE).first()
    if m is None:
        raise NotFound("not_a_member")
    u, track = m.user, cls.track
    assignments = list(cls.assignments.select_related("deck"))
    row = next(r for r in student_rows(cls, assignments) if r["id"] == u.id)
    day = today()
    acts = {a.date: a for a in DailyActivity.objects.filter(user=u, date__gte=day - timedelta(days=13))}
    chart = []
    for i in range(13, -1, -1):
        d = day - timedelta(days=i)
        a = acts.get(d)
        chart.append({"date": d.isoformat(), "xp": a.xp if a else 0, "correct": a.correct if a else 0})
    mistakes = [
        {"term": w.term, "translation": w.translation_uz, "misses": w.miss_count, "box": w.box}
        for w in UserWord.objects.filter(user=u, track=track, miss_count__gt=0).order_by("-miss_count", "term")[:20]
    ]
    from words.levels import progress as level_progress

    levels = [{"level": r["level"], "percent": r.get("percent", 0)} for r in level_progress(u, track)]
    return {
        "student": row,
        "assignments": [{**assignment_dict(a), "progress": row["assignments"].get(str(a.id))} for a in assignments],
        "chart": chart,
        "mistakes": mistakes,
        "levels": levels,
    }


def hardest_words(cls: Classroom, limit: int = 20) -> list[dict]:
    ids = student_ids(cls)
    rows = (
        UserWord.objects.filter(user_id__in=ids, track=cls.track, miss_count__gt=0)
        .values("term_key")
        .annotate(students=Count("user_id", distinct=True), misses=Sum("miss_count"))
        .order_by("-students", "-misses", "term_key")[:limit]
    )
    keys = [r["term_key"] for r in rows]
    sample = {}
    for uw in UserWord.objects.filter(user_id__in=ids, track=cls.track, term_key__in=keys).select_related("word"):
        cur = sample.get(uw.term_key)
        if cur is None or (not cur.translation_uz and uw.translation_uz) or (not cur.word_id and uw.word_id):
            sample[uw.term_key] = uw
    out = []
    for r in rows:
        uw = sample[r["term_key"]]
        translation = (uw.word.translation_uz if uw.word_id else "") or uw.translation_uz
        out.append(
            {
                "term": uw.word.display if uw.word_id else uw.term,
                "translation": translation,
                "students": r["students"],
                "misses": r["misses"],
            }
        )
    return out


def deck_from_hardest(cls: Classroom, user, terms: list[str] | None, due_at, target: int = 80) -> Assignment:
    """ "Shu so'zlardan deck yaratish va biriktirish": a private deck of the teacher + a deck assignment."""
    from decks.models import Card, Deck

    words = hardest_words(cls, limit=50)
    if terms:
        wanted = {term_key(t) for t in terms}
        words = [w for w in words if term_key(w["term"]) in wanted]
    if not words:
        raise ValidationError({"detail": "no_words"})
    with transaction.atomic():
        deck = Deck.objects.create(
            owner=user,
            name=f"{cls.name}: qiyin so'zlar"[:120],
            track=cls.track,
            translation_lang="uz",
            description="Sinfda eng ko'p xato qilingan so'zlar",
        )
        Card.objects.bulk_create(
            [Card(deck=deck, term=w["term"], translation=w["translation"] or "—", order=i) for i, w in enumerate(words)]
        )
        return create_assignment(
            cls,
            user,
            {"kind": Assignment.DECK, "deck": deck.id, "due_at": due_at, "target_value": target, "title": deck.name},
        )


def leaderboard(cls: Classroom, me_id: int | None = None) -> list[dict]:
    ms = list(M.objects.filter(classroom=cls, status=M.ACTIVE).select_related("user"))
    weekly = _by_user(
        DailyActivity.objects.filter(user_id__in=[m.user_id for m in ms], date__gte=week_start())
        .values("user_id")
        .annotate(n=Sum("xp"))
    )
    ranked = sorted(ms, key=lambda m: (-weekly.get(m.user_id, 0), m.user.display_name.lower()))
    return [
        {"rank": i + 1, **person(m.user), "xp": weekly.get(m.user_id, 0), "is_me": m.user_id == me_id}
        for i, m in enumerate(ranked)
    ]


def student_view(cls: Classroom, user) -> dict:
    """A student's class page: assignments with their own progress, and the class leaderboard."""
    assignments = list(cls.assignments.select_related("deck"))
    now = timezone.now()
    items = []
    for a in assignments:
        p = progress(a, [user.id], now)[user.id]
        items.append({**assignment_dict(a), "progress": p})
    return {
        "class": class_dict(cls, user, teacher=False),
        "assignments": items,
        "leaderboard": leaderboard(cls, user.id),
    }


def export_csv(cls: Classroom) -> str:
    assignments = list(cls.assignments.select_related("deck"))
    rows = [r for r in student_rows(cls, assignments) if r["membership"] == M.ACTIVE]
    buf = io.StringIO()
    w = csv.writer(buf)
    head = ["Ism", "Oxirgi faollik", "So'zlar (hafta)", "So'zlar (jami)", "Aniqlik %", "Streak", "Haftalik XP"]
    w.writerow(head + [f"{a.title} (%)" for a in assignments] + [f"{a.title} (holat)" for a in assignments])
    for r in rows:
        cells = [r["assignments"][str(a.id)] for a in assignments]
        w.writerow(
            [
                r["name"],
                r["last_active"] or "",
                r["words_week"],
                r["words_total"],
                "" if r["accuracy"] is None else r["accuracy"],
                r["streak"],
                r["weekly_xp"],
            ]
            + [
                c["percent"] if a.target_kind == Assignment.LEARN else c["plays"]
                for a, c in zip(assignments, cells, strict=True)
            ]
            + [c["status"] for c in cells]
        )
    return "﻿" + buf.getvalue()  # BOM: Excel opens UTF-8 (o', g', Cyrillic) correctly


def announce(cls: Classroom, user, text: str):
    """Send a message to every student of the class through the Broadcast sender (batching, 429 / 403)."""
    from html import escape

    from broadcasts import services as bsvc
    from broadcasts.models import Broadcast

    from .models import Announcement

    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": "empty"})
    body = f"📣 <b>{escape(cls.name)}</b>\n\n{escape(text)}"
    b = Broadcast.objects.create(
        text=body,
        audience="class",
        audience_ref=str(cls.id),
        button_kind="webapp",
        button_text="Sinfni ochish",
        webapp_path=f"/classes/{cls.id}",
        created_by=user,
    )
    ann = Announcement.objects.create(classroom=cls, author=user, text=text, broadcast=b)
    if settings.TELEGRAM_BOT_TOKEN:
        bsvc.start(b.pk)  # busy with another broadcast → stays queued, the hourly cron starts it
    return ann
