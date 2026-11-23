"""Pre-generate audio of the built-in words and example sentences.

Idempotent and resumable: existing audio is skipped, every file is written on its own.
Target: the S3 bucket when S3_* is set, else backend/tts_audio/ (commit it; whitenoise serves it).
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from tts import storage
from tts.providers import TtsError, get_provider
from tts.services import MAX_CHARS, resolve
from tts.text import spoken_text
from words.models import Word


def jobs(langs, voices_mode: str, rates, examples: bool):
    provider = get_provider()
    seen = set()
    for lang in langs:
        voices = provider.voices[lang] if voices_mode == "all" else provider.voices[lang][:1]
        for w in Word.objects.filter(track=lang).order_by("level", "id"):
            texts = [(w.display, rates)] + ([(w.example, ["normal"])] if examples and w.example else [])
            for raw, speeds in texts:
                text = spoken_text(raw, lang)
                if not text or len(text) > MAX_CHARS:
                    continue
                for v in voices:
                    for rate in speeds:
                        _, voice, speed, key = resolve(text, lang, rate, v.id)
                        if key not in seen:
                            seen.add(key)
                            yield key, text, voice, speed


class Command(BaseCommand):
    help = "Generate MP3 files for level words, exam pack words and example sentences."

    def add_arguments(self, parser):
        parser.add_argument("--lang", choices=["de", "en"], help="Only this language.")
        parser.add_argument("--voices", choices=["default", "all"], default="default")
        parser.add_argument("--slow", action="store_true", help="Also the slow version of the words.")
        parser.add_argument("--no-examples", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Stop after N new files (run again to continue).")
        parser.add_argument("--rps", type=float, default=8, help="Requests per second.")
        parser.add_argument("--dry-run", action="store_true", help="Only count files and characters.")

    def handle(self, *args, **o):
        provider = get_provider()
        langs = [o["lang"]] if o["lang"] else ["de", "en"]
        rates = ["normal", "slow"] if o["slow"] else ["normal"]
        todo = [j for j in jobs(langs, o["voices"], rates, not o["no_examples"]) if not storage.find(j[0])]
        chars = sum(len(j[1]) for j in todo)
        self.stdout.write(f"{len(todo)} files to generate, {chars} characters ({provider.name}).")
        if o["dry_run"] or not todo:
            return
        if not provider.configured():
            raise CommandError("No TTS credentials (GOOGLE_TTS_CREDENTIALS_JSON or AZURE_TTS_KEY + AZURE_TTS_REGION).")
        if o["limit"]:
            todo = todo[: o["limit"]]
        done = failed = streak = 0
        for key, text, voice, speed in todo:
            data = None
            for attempt in range(3):
                try:
                    data = provider.synthesize(text, voice, speed)
                    break
                except TtsError as exc:
                    self.stderr.write(f"{text}: {exc}")
                    time.sleep(2**attempt if o["rps"] > 0 else 0)
            if data is None:
                failed += 1
                streak += 1
                if streak >= 5:
                    raise CommandError(f"5 failures in a row; {done} files are done. Run again to continue.")
                continue
            streak = 0
            if storage.s3_enabled():
                storage.save_s3(key, data)
            else:
                storage.save_static(key, data)
            done += 1
            if done % 100 == 0:
                self.stdout.write(f"  {done}/{len(todo)}")
            if o["rps"] > 0:
                time.sleep(1 / o["rps"])
        self.stdout.write(self.style.SUCCESS(f"{done} files generated, {failed} failed."))
