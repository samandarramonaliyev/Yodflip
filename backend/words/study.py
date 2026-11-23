"""Word list study mode: word → translation → example. Reading never changes progress."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError

from .leitner import MAX_BOX
from .models import UserLevelWord, UserWord, term_key
from .translations import apply_translations, resolve

LESSON = 20


def study_page(request, track: str, words, topics: list[tuple[str, str, dict]], topic_of) -> dict:
    """`words`: ordered queryset (topic filter applied), `topics`: (slug, emoji, names)."""
    from games.sources import item_from_word

    p, user = request.query_params, request.user
    lang, _ = resolve(track, p.get("lang"))
    try:
        lesson = max(1, int(p.get("lesson") or 1))
    except ValueError:
        raise ValidationError({"lesson": "invalid"}) from None
    rows = list(words)
    found = set(
        UserLevelWord.objects.filter(user=user, track=track, found_at__isnull=False).values_list("word_id", flat=True)
    )
    mine = {u.term_key: u for u in UserWord.objects.filter(user=user, track=track)}

    def learned(w) -> bool:
        u = mine.get(term_key(w.display))
        return w.id in found or bool(u and u.box >= MAX_BOX)

    if (p.get("only_unlearned") or "").lower() in ("1", "true"):
        rows = [w for w in rows if not learned(w)]
    items = {i["word_id"]: i for i in apply_translations([item_from_word(w) for w in rows], lang)}
    q = " ".join((p.get("search") or "").lower().split())
    if q:
        rows = [w for w in rows if q in w.display.lower() or q in items[w.id]["translation"].lower()]
    total = len(rows)
    lessons = max(1, (total + LESSON - 1) // LESSON)
    lesson = min(lesson, lessons)
    start = (lesson - 1) * LESSON
    out = []
    for w in rows[start : start + LESSON]:
        i, u = items[w.id], mine.get(term_key(w.display))
        out.append(
            {
                "id": w.id,
                "term": w.display,
                "word": w.word,
                "article": w.article,
                "pos": w.part_of_speech,
                "definition": w.definition,
                "translation": i["translation"],
                "translation_uz": w.translation_uz,
                "example": w.example,
                "example_tr": i["example_tr"],
                "topic": topic_of(w),
                "learned": learned(w),
                "want": bool(u and u.want_to_learn),
                "userword_id": u.id if u else None,
            }
        )
    return {
        "track": track,
        "lang": lang,
        "lesson": lesson,
        "lessons": lessons,
        "lesson_size": LESSON,
        "total": total,
        "topics": [{"slug": s, "emoji": e, "name": n} for s, e, n in topics],
        "words": out,
    }
