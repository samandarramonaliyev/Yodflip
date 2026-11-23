"""Exam packs: progress, rounds, daily goal, badges and the exam simulation."""

from __future__ import annotations

import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from gamification.models import GameSession
from gamification.services import check_achievements, grant, record_activity, today
from words.levels import Round, assemble_round
from words.models import LevelRound, UserLevelWord, Word, WordTranslation
from words.services import apply_answer
from words.translations import resolve

from .models import ExamGoal, ExamPack, ExamSimulation, PackWord

SIM_QUESTIONS = 30
SIM_SECONDS = 600
SIM_GRACE = 30
WEAK_PERCENT = 70
XP_PER_CORRECT = 5
MAX_VIOLATIONS = 3
VIOLATIONS = ("tab_switch", "focus_loss", "printscreen", "copy", "devtools")


def get_pack(slug: str, track: str | None = None) -> ExamPack:
    pack = ExamPack.objects.filter(slug=slug).first()
    if pack is None:
        raise NotFound("pack_not_found")
    if track and pack.track != track:
        raise ValidationError({"track": "track_mismatch"})
    return pack


def topic_list(topic: str) -> list[str]:
    return [t for t in (topic or "").split(",") if t][:30]


def pack_words(pack: ExamPack, topic: str = ""):
    """Words of a pack in order; `topic` = one slug or several separated by commas."""
    q = Q(exam_links__pack=pack)
    if topic_list(topic):
        q &= Q(exam_links__topic__slug__in=topic_list(topic))
    return Word.objects.filter(q).order_by("exam_links__order")


def _names(o) -> dict:
    return {"uz": o.name_uz, "en": o.name_en, "ru": o.name_ru}


def _found_links(user):
    return PackWord.objects.filter(word__level_progress__user=user, word__level_progress__found_at__isnull=False)


def _percent(found: int, total: int) -> int:
    return 100 * found // total if total else 0


def pack_list(user, track: str) -> list[dict]:
    found = dict(_found_links(user).order_by().values_list("pack_id").annotate(n=Count("id")))
    rows = []
    for p in ExamPack.objects.filter(track=track).annotate(
        words=Count("pack_words", distinct=True), topic_count=Count("topics", distinct=True)
    ):
        f = found.get(p.id, 0)
        rows.append(
            {
                "slug": p.slug,
                "track": p.track,
                "emoji": p.emoji,
                "name": _names(p),
                "total": p.words,
                "topic_count": p.topic_count,
                "found": f,
                "percent": _percent(f, p.words),
            }
        )
    return rows


def progress_row(user, track: str, slug: str) -> dict:
    """Same shape as a level progress row, so level and exam rounds share the result screens."""
    pack = get_pack(slug, track)
    total = pack.pack_words.count()
    found = _found_links(user).filter(pack=pack).count()
    return {
        "level": pack.slug,
        "exam": pack.slug,
        "name": _names(pack),
        "total": total,
        "found": found,
        "learned": found,
        "remaining": total - found,
        "percent": _percent(found, total),
        "unlock_target": 0,
        "to_unlock": 0,
        "unlocked": True,
        "completed": total > 0 and found >= total,
    }


def detail(user, pack: ExamPack) -> dict:
    found = dict(_found_links(user).filter(pack=pack).order_by().values_list("topic_id").annotate(n=Count("id")))
    topics = []
    for t in pack.topics.annotate(n=Count("pack_words")):
        f = found.get(t.id, 0)
        topics.append(
            {
                "slug": t.slug,
                "emoji": t.emoji,
                "name": _names(t),
                "total": t.n,
                "found": f,
                "percent": _percent(f, t.n),
            }
        )
    last = ExamSimulation.objects.filter(user=user, pack=pack, finished_at__isnull=False).first()
    return {
        **progress_row(user, pack.track, pack.slug),
        "slug": pack.slug,
        "track": pack.track,
        "emoji": pack.emoji,
        "topics": topics,
        "next_topic": next_topic(user, pack, topics),
        "goal": goal_for(user, pack),
        "last_simulation": {"score": last.score, "total": len(last.questions)} if last else None,
    }


def next_topic(user, pack: ExamPack, topics: list[dict]) -> str | None:
    """ "Boshlash": the topic played last if it is unfinished, else the first unfinished one."""
    open_ = [t["slug"] for t in topics if t["found"] < t["total"]]
    last = (
        LevelRound.objects.filter(user=user, exam=pack.slug).exclude(topic="").values_list("topic", flat=True).first()
    )
    return last if last in open_ else (open_[0] if open_ else None)


def build_round(user, pack: ExamPack, size: int, *, game: str = "", topic: str = "") -> Round:
    all_ids = list(pack_words(pack).values_list("id", flat=True))
    qs = pack_words(pack, topic)
    if game == "derdiedas":
        qs = qs.filter(article__in=["der", "die", "das"])
    pool = list(qs.values_list("id", flat=True))
    return assemble_round(user, pack.track, all_ids, pool, size, game=game, exam=pack.slug, topic=topic)


def award_badges(user, word_ids: list[int]) -> None:
    """Pack 50% / 100% badges for every pack that contains one of the newly found words."""
    for pack in ExamPack.objects.filter(pack_words__word_id__in=word_ids).distinct():
        total = pack.pack_words.count()
        found = _found_links(user).filter(pack=pack).count()
        if total and 2 * found >= total:
            grant(user, "exam_pack_50")
        if total and found >= total:
            grant(user, "exam_pack_100")


# --------------------------------------------------------------------------- daily goal
def found_today(user, pack: ExamPack) -> int:
    return UserLevelWord.objects.filter(user=user, word__exam_links__pack=pack, found_at__date=today()).count()


def goal_for(user, pack: ExamPack | None = None) -> dict | None:
    """The user's daily goal (only if it is for `pack`, when given)."""
    goal = ExamGoal.objects.select_related("pack").filter(user=user).first()
    if goal is None or (pack and goal.pack_id != pack.pk):
        return None
    done = found_today(user, goal.pack)
    return {
        "slug": goal.pack.slug,
        "track": goal.pack.track,
        "emoji": goal.pack.emoji,
        "name": _names(goal.pack),
        "per_day": goal.per_day,
        "done": done,
        "reached": done >= goal.per_day,
    }


def set_goal(user, pack: ExamPack, per_day: int) -> dict | None:
    if per_day <= 0:
        ExamGoal.objects.filter(user=user, pack=pack).delete()
        return None
    ExamGoal.objects.update_or_create(user=user, defaults={"pack": pack, "per_day": min(per_day, 100)})
    return goal_for(user)


# --------------------------------------------------------------------------- simulation
def _pick(by_topic: dict[str, list[Word]], count: int, rng) -> list[tuple[str, Word]]:
    """Spread the questions over all topics (round robin), then shuffle."""
    for ws in by_topic.values():
        rng.shuffle(ws)
    slugs = list(by_topic)
    rng.shuffle(slugs)
    out: list[tuple[str, Word]] = []
    while len(out) < count and any(by_topic.values()):
        for s in slugs:
            if by_topic[s] and len(out) < count:
                out.append((s, by_topic[s].pop()))
    rng.shuffle(out)
    return out


def _options(answer: str, pool: list[str], rng) -> list[str]:
    seen = {answer.lower()}
    opts = [answer]
    for p in rng.sample(pool, min(len(pool), 60)):
        if p and p.lower() not in seen:
            seen.add(p.lower())
            opts.append(p)
        if len(opts) == 4:
            break
    rng.shuffle(opts)
    return opts


def start_simulation(user, pack: ExamPack, lang: str, rng=None) -> ExamSimulation:
    rng = rng or random.SystemRandom()
    lang, _ = resolve(pack.track, lang)
    links = list(pack.pack_words.select_related("word", "topic"))
    if len(links) < SIM_QUESTIONS:
        raise ValidationError({"detail": "not_enough_words"})
    by_topic: dict[str, list[Word]] = {}
    for link in links:
        by_topic.setdefault(link.topic.slug, []).append(link.word)
    words = [link.word for link in links]
    texts = dict(WordTranslation.objects.filter(word__in=words, lang=lang).values_list("word_id", "text"))
    pools = {
        "translation": [texts.get(w.id, "") for w in words],
        "reverse": [w.display for w in words],
        "definition": [w.display for w in words],
    }
    questions = []
    for n, (topic, w) in enumerate(_pick(by_topic, SIM_QUESTIONS, rng)):
        kind = ("translation", "reverse", "definition")[n % 3]
        if kind == "definition":
            prompt, answer = w.definition, w.display
        elif kind == "reverse":
            prompt, answer = texts.get(w.id) or w.translation_uz, w.display
        else:
            prompt, answer = w.display, texts.get(w.id) or w.translation_uz
        options = _options(answer, pools[kind], rng)
        questions.append(
            {
                "kind": kind,
                "topic": topic,
                "word_id": w.id,
                "term": w.display,
                "prompt": prompt,
                "options": options,
                "answer": options.index(answer),
            }
        )
    return ExamSimulation.objects.create(
        user=user, pack=pack, translation_lang=lang, questions=questions, time_limit=SIM_SECONDS
    )


def simulation_payload(sim: ExamSimulation) -> dict:
    return {
        "id": sim.pk,
        "pack": sim.pack.slug,
        "name": _names(sim.pack),
        "time_limit": sim.time_limit,
        "total": len(sim.questions),
        "max_violations": MAX_VIOLATIONS,
        "question": current_question(sim),
    }


def current_question(sim: ExamSimulation) -> dict | None:
    """Only the current question, never the answer."""
    if sim.finished_at or sim.position >= len(sim.questions):
        return None
    q = sim.questions[sim.position]
    return {"index": sim.position, "kind": q["kind"], "prompt": q["prompt"], "options": q["options"]}


def _deadline(sim: ExamSimulation):
    return sim.created_at + timedelta(seconds=sim.time_limit + SIM_GRACE)


def _locked(user, sim_id: int) -> ExamSimulation:
    sim = ExamSimulation.objects.select_for_update().filter(pk=sim_id, user=user).first()
    if sim is None:
        raise NotFound("simulation_not_found")
    return sim


def answer_question(user, sim_id: int, index: int, choice: int | None) -> dict:
    """Store one answer (None = skipped) and return the next question. No feedback before submitting."""
    with transaction.atomic():
        sim = _locked(user, sim_id)
        if sim.finished_at or timezone.now() > _deadline(sim):
            return {"done": True, "question": None}
        if index == sim.position and index < len(sim.questions):  # a repeated post changes nothing
            if choice is not None:
                if choice >= len(sim.questions[index]["options"]):
                    raise ValidationError({"choice": "invalid"})
                sim.answers = {**sim.answers, str(index): choice}
            sim.position += 1
            sim.save(update_fields=["answers", "position"])
        q = current_question(sim)
        return {"done": q is None, "question": q}


def record_violation(user, sim_id: int, kind: str) -> dict:
    """Count a violation; the third one finishes the exam without XP and badges."""
    with transaction.atomic():
        sim = _locked(user, sim_id)
        if not sim.finished_at:
            sim.violations = [*sim.violations, {"kind": kind, "at": timezone.now().isoformat()}]
            if len(sim.violations) >= MAX_VIOLATIONS:
                sim.terminated = True
            sim.save(update_fields=["violations", "terminated"])
        result = submit_simulation(user, sim_id) if sim.terminated else None
        return {"count": len(sim.violations), "max": MAX_VIOLATIONS, "terminated": sim.terminated, "result": result}


def score_simulation(questions: list[dict], answers: dict[int, int]) -> dict:
    """Pure scoring: total score and per-topic results; unanswered = wrong."""
    topics: dict[str, dict] = {}
    score = 0
    for n, q in enumerate(questions):
        ok = answers.get(n) == q["answer"]
        score += ok
        t = topics.setdefault(q["topic"], {"slug": q["topic"], "correct": 0, "total": 0})
        t["total"] += 1
        t["correct"] += ok
    rows = []
    for t in topics.values():
        percent = round(100 * t["correct"] / t["total"])
        rows.append({**t, "percent": percent, "weak": percent < WEAK_PERCENT})
    rows.sort(key=lambda r: (r["percent"], -r["total"]))
    total = len(questions)
    return {
        "score": score,
        "total": total,
        "percent": round(100 * score / total) if total else 0,
        "topics": rows,
        "weak_topics": [r["slug"] for r in rows if r["weak"]],
    }


def submit_simulation(user, sim_id: int) -> dict:
    """Score the stored answers once; the same result is returned for repeated submits."""
    with transaction.atomic():
        sim = _locked(user, sim_id)
        if sim.finished_at:
            return sim.result
        now = timezone.now()
        answers = {int(k): v for k, v in sim.answers.items()}
        late = now > _deadline(sim)
        res = score_simulation(sim.questions, answers)
        names = {t.slug: t for t in sim.pack.topics.all()}
        for row in res["topics"]:
            t = names.get(row["slug"])
            row["name"] = _names(t) if t else {"uz": row["slug"], "en": row["slug"], "ru": row["slug"]}
            row["emoji"] = t.emoji if t else "📚"
        duration = int((now - sim.created_at).total_seconds() * 1000)
        xp = 0
        if not sim.terminated:  # a terminated exam gives no XP, badges or learning progress
            for n, choice in answers.items():
                q = sim.questions[n]
                item = {"term": q["term"], "word_id": q["word_id"]}
                apply_answer(user, sim.pack.track, item, choice == q["answer"])
            user.refresh_from_db()
            xp = 0 if late else XP_PER_CORRECT * res["score"]
            GameSession.objects.create(
                user=user,
                track=sim.pack.track,
                game="exam_sim",
                mode="memorize",
                source=f"exam:{sim.pack.slug}"[:40],
                translation_lang=sim.translation_lang,
                xp=xp,
                correct=res["score"],
                attempts=res["total"],
                duration_ms=duration,
            )
            record_activity(user, xp, res["score"], res["total"])
            check_achievements(user)
        review = [
            {
                "prompt": q["prompt"],
                "answer": q["options"][q["answer"]],
                "given": q["options"][answers[n]] if n in answers else None,
                "correct": answers.get(n) == q["answer"],
            }
            for n, q in enumerate(sim.questions)
        ]
        res.update(
            xp=xp,
            late=late,
            duration_ms=duration,
            streak=user.streak,
            xp_total=user.xp,
            review=review,
            terminated=sim.terminated,
            violations=sim.violations,
        )
        sim.score, sim.result, sim.finished_at = res["score"], res, now
        sim.save(update_fields=["score", "result", "finished_at"])
    return res
