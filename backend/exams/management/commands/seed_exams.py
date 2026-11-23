"""Load the exam packs (idempotent). Existing Word records are reused; words are never deleted.

Run after seed_words. Skips when exactly this seed was already loaded (--force reloads).
"""

from __future__ import annotations

import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import SeedState
from exams.models import ExamPack, ExamTopic, PackWord
from exams.seedfiles import SEED_DIR, check, load_all
from words.levels import backfill_from_leitner
from words.management.commands.seed_words import other_lang, split_article
from words.models import Word, WordTranslation, term_key

KEY = "exam_packs"


class Command(BaseCommand):
    help = "Seed the exam preparation packs."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **opts):
        files = sorted(SEED_DIR.rglob("*.txt"))
        digest = hashlib.sha256(b"".join(f.name.encode() + f.read_bytes() for f in files)).hexdigest()
        state = SeedState.objects.filter(key=KEY).first()
        if state and state.digest == digest and PackWord.objects.exists() and not opts["force"]:
            self.stdout.write("Exam packs unchanged, already loaded. Skipping (use --force to reload).")
            return
        _, errors = check()
        if errors:
            raise CommandError("\n".join(errors[:20]))
        packs, _ = load_all()
        with transaction.atomic():
            index = {(w.track, term_key(w.display)): w for w in Word.objects.all()}
            for p in packs:
                self._words(p, index)
            for order, p in enumerate(packs):
                self._links(p, order, index)
            SeedState.objects.update_or_create(key=KEY, defaults={"digest": digest})
            # Words learned earlier (e.g. in a deck) count as found in the packs too.
            backfill_from_leitner()
        self.stdout.write(self.style.SUCCESS("Exam packs seeded."))

    def _words(self, p, index) -> None:
        track = p.info.track
        create, update = [], []
        fields = ["part_of_speech", "definition", "translation_uz", "example", "example_uz"]
        for key, r in p.new.items():
            word, article = split_article(r["raw"], track)
            w = index.get((track, key))
            if w is not None and w.level:
                continue  # became a level word: the level seed owns its texts
            values = {
                "part_of_speech": r["pos"],
                "definition": r["definition"],
                "translation_uz": r["uz"],
                "example": r["example"],
                "example_uz": r["example_uz"],
            }
            if w is None:
                w = Word(track=track, level="", pack=None, word=word, article=article, **values)
                create.append(w)
                index[track, key] = w
            else:
                for f, v in values.items():
                    setattr(w, f, v)
                update.append(w)
        Word.objects.bulk_create(create, batch_size=500)
        Word.objects.bulk_update(update, fields, batch_size=500)
        rows = []
        for w in (*create, *update):
            r = p.new[term_key(w.display)]
            for lang, text, ex in (
                ("uz", r["uz"], r["example_uz"]),
                ("ru", r["ru"], r["example_ru"]),
                (other_lang(track), r["other"], r["example_other"]),
            ):
                rows.append(WordTranslation(word=w, lang=lang, text=text, example_translation=ex))
        WordTranslation.objects.bulk_create(
            rows,
            batch_size=500,
            update_conflicts=True,
            unique_fields=["word", "lang"],
            update_fields=["text", "example_translation"],
        )
        extra = []
        for key, (coll, family) in p.extra.items():
            w = index[track, key]
            w.collocations, w.word_family = coll, family
            extra.append(w)
        Word.objects.bulk_update(extra, ["collocations", "word_family"], batch_size=500)

    def _links(self, p, order: int, index) -> None:
        i = p.info
        pack, _ = ExamPack.objects.update_or_create(
            slug=i.slug,
            defaults={
                "track": i.track,
                "emoji": i.emoji,
                "name_uz": i.name_uz,
                "name_en": i.name_en,
                "name_ru": i.name_ru,
                "order": order,
            },
        )
        links, n = [], 0
        for t_order, t in enumerate(p.topics):
            names = {k: t[k] for k in ("emoji", "name_en", "name_uz", "name_ru")}
            topic, _ = ExamTopic.objects.update_or_create(
                pack=pack, slug=t["slug"], defaults={**names, "order": t_order}
            )
            for raw in t["words"]:
                links.append(PackWord(pack=pack, topic=topic, word=index[i.track, term_key(raw)], order=n))
                n += 1
        PackWord.objects.bulk_create(
            links,
            batch_size=500,
            update_conflicts=True,
            unique_fields=["pack", "word"],
            update_fields=["topic", "order"],
        )
        # Words taken out of a list are unlinked (the Word and its progress stay).
        pack.pack_words.exclude(word_id__in=[x.word_id for x in links]).delete()
        pack.topics.exclude(slug__in=[t["slug"] for t in p.topics]).delete()
