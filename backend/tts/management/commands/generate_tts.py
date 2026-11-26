"""Pre-generate audio of the built-in words and example sentences.

Words go to TTS_WORDS_PROVIDER (ElevenLabs), example sentences to TTS_SENTENCES_PROVIDER (Google/Azure).
Idempotent and resumable: audio that exists for any provider of the chain is never generated again.
Credit-safe: the character count and estimated ElevenLabs credits are printed first; --dry-run stops there.
When ElevenLabs refuses (quota used up, 401/429) the remaining texts go to the fallback provider; when no
provider is left they are skipped and the app plays the browser voice for them.
Target: the S3 bucket when S3_* is set, else backend/tts_audio/ (commit it; whitenoise serves it).
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tts import storage
from tts.providers import ElevenLabsProvider, QuotaExceeded, TtsError, TTSProvider, Voice
from tts.services import MAX_CHARS, candidates
from tts.text import spoken_text
from words.models import Word


@dataclass
class Job:
    text: str
    lang: str
    kind: str
    options: list[tuple[TTSProvider, Voice, float, str]]  # routing order: preferred provider first

    @property
    def planned(self) -> TTSProvider:
        """The provider that will be asked first: the preferred one if it has credentials."""
        return next((p for p, *_ in self.options if p.configured()), self.options[0][0])


def jobs(langs, voices_mode: str, rates, examples: bool):
    seen = set()
    for lang in langs:
        for w in Word.objects.filter(track=lang).order_by("level", "id"):
            texts = [(w.display, rates, "word")]
            if examples and w.example:
                texts.append((w.example, ["normal"], "sentence"))
            for raw, speeds, kind in texts:
                text = spoken_text(raw, lang)
                if not text or len(text) > MAX_CHARS:
                    continue
                first = candidates(text, lang, kind=kind)[0][0]
                voice_ids = [v.id for v in first.voices[lang]] if voices_mode == "all" else [""]
                for vid in voice_ids:
                    for rate in speeds:
                        options = candidates(text, lang, rate, vid, kind)
                        if options[0][3] not in seen:
                            seen.add(options[0][3])
                            yield Job(text, lang, kind, options)


def exists(job: Job, upgrade: bool) -> bool:
    keys = [job.options[0][3]] if upgrade else [o[3] for o in job.options]
    return any(storage.find(k) for k in keys)


def credits_left() -> int | None:
    """Remaining ElevenLabs credits, or None when the key may not read them (needs the user_read permission)."""
    try:
        r = httpx.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": settings.ELEVENLABS_API_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            return int(d["character_limit"]) - int(d["character_count"])
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        pass
    return None


class Command(BaseCommand):
    help = "Generate MP3 files for level words, exam pack words and example sentences."

    def add_arguments(self, parser):
        parser.add_argument("--lang", choices=["de", "en"], help="Only this language.")
        parser.add_argument("--voices", choices=["default", "all"], default="default")
        parser.add_argument("--slow", action="store_true", help="Also the slow version of the words.")
        parser.add_argument("--no-examples", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Only the first N new files (run again to continue).")
        parser.add_argument("--rps", type=float, default=4, help="Requests per second.")
        parser.add_argument("--dry-run", action="store_true", help="Only count files, characters and credits.")
        parser.add_argument(
            "--upgrade",
            action="store_true",
            help="Also make the preferred provider's audio where only fallback audio exists (spends credits).",
        )

    def handle(self, *args, **o):
        langs = [o["lang"]] if o["lang"] else ["de", "en"]
        rates = ["normal", "slow"] if o["slow"] else ["normal"]
        todo = [j for j in jobs(langs, o["voices"], rates, not o["no_examples"]) if not exists(j, o["upgrade"])]
        if o["limit"]:
            todo = todo[: o["limit"]]
        self.report(todo)
        if o["dry_run"] or not todo:
            return
        if not any(p.configured() for j in todo for p, *_ in j.options):
            raise CommandError(
                "No TTS credentials "
                "(ELEVENLABS_API_KEY, GOOGLE_TTS_CREDENTIALS_JSON or AZURE_TTS_KEY + AZURE_TTS_REGION)."
            )
        self.generate(todo, o["rps"])

    def report(self, todo: list[Job]) -> None:
        files, chars = Counter(), Counter()
        for j in todo:
            files[j.planned.name] += 1
            chars[j.planned.name] += len(j.text)
        self.stdout.write(f"{len(todo)} files to generate, {sum(chars.values())} characters.")
        for name in files:
            self.stdout.write(f"  {name}: {files[name]} files, {chars[name]} characters")
        el = chars.get(ElevenLabsProvider.name, 0)
        if not el:
            return
        need = ElevenLabsProvider.credits(el)
        self.stdout.write(f"  Estimated ElevenLabs credits: {need:.0f} ({settings.ELEVENLABS_MODEL})")
        left = credits_left()
        if left is not None:
            self.stdout.write(f"  ElevenLabs credits left: {left}")
            if left < need:
                self.stdout.write(self.style.WARNING("  Not enough credits: the rest will use the fallback provider."))

    def generate(self, todo: list[Job], rps: float) -> None:
        dead: set[str] = set()  # providers that refused with a quota error in this run
        done, skipped, failed, streak = Counter(), 0, 0, 0
        for n, job in enumerate(todo, 1):
            data = provider = key = None
            for p, voice, speed, k in job.options:
                if p.configured() and p.name not in dead:
                    data = self.synthesize(p, job.text, voice, speed, rps, dead, done)
                    if data is not None:
                        provider, key = p, k
                        break
            if data is None:
                if all(not p.configured() or p.name in dead for p, *_ in job.options):
                    skipped += 1  # no provider left: the app plays the browser voice
                    continue
                failed += 1
                streak += 1
                if streak >= 5:
                    total = sum(done.values())
                    raise CommandError(f"5 failures in a row; {total} files are done. Run again to continue.")
                continue
            streak = 0
            if storage.s3_enabled():
                storage.save_s3(key, data)
            else:
                storage.save_static(key, data)
            done[provider.name] += 1
            if n % 100 == 0:
                self.stdout.write(f"  {n}/{len(todo)}")
            if rps > 0:
                time.sleep(1 / rps)
        by = ", ".join(f"{k}: {v}" for k, v in done.items()) or "none"
        msg = f"{sum(done.values())} files generated ({by}), {failed} failed"
        if skipped:
            msg += f", {skipped} left for the browser voice (run again later to fill them)"
        self.stdout.write(self.style.SUCCESS(msg + "."))

    def synthesize(self, provider, text, voice, speed, rps, dead, done) -> bytes | None:
        for attempt in range(3):
            try:
                return provider.synthesize(text, voice, speed)
            except QuotaExceeded as exc:
                dead.add(provider.name)
                self.stdout.write(
                    self.style.WARNING(
                        f"{exc}: stopped {provider.name} after {done[provider.name]} files; "
                        "the remaining texts use the fallback provider."
                    )
                )
                return None
            except TtsError as exc:
                self.stderr.write(f"{text}: {exc}")
                time.sleep(2**attempt if rps > 0 else 0)
        return None
