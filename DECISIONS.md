# Decisions & assumptions

Everything that was not fully specified, and what was chosen.

## Product
- **Name**: kept **WordFlip** (short, describes the card-flip mechanic, works in all three UI languages).
- **Extra game**: **Memory Pairs**, a classic concentration board with word and Uzbek cards mixed (memorization game, has the reverse toggle).
- **Word Builder direction**: the default prompt is Uzbek and the player builds the foreign word, as the spec says. The reverse toggle flips it (word shown, build the Uzbek). The same applies to **Falling Words** (Uzbek falls by default).
- **Review Mode and Daily Challenge** both use a multiple-choice quiz (word → Uzbek, 4 options). When the pool has no distractors at all (a single word), the quiz switches to typing.
- **Daily Challenge**: 10 words picked deterministically from A1–B2 per track and day (`seed = track + date`). Only the **first** attempt goes on the leaderboard and earns XP. Score = 100 per correct answer + a speed bonus (≤ 300 when all 10 are right, ≤ 90 otherwise), so accuracy always beats speed.
- **Match Game rounds**: Easy 4 / Medium 6 / Hard 8 pairs. A tail smaller than 3 pairs is merged into the last round. Words and definitions are shuffled independently. Only one word and one definition card can be face-up at a time. Long definitions (> 70 chars) are clamped to 4 lines with an expand button.
- **Match Game Leitner**: answers are applied in order. A miss sends the word to box 1, and a later match in the same round moves it up again (box 2), exactly following "miss → box 1, match → +1".
- **Leitner intervals** (days until due): box 1 → 0, 2 → 1, 3 → 3, 4 → 7, 5 → 14. "Review" = words already seen whose `due_at` has passed.
- **Unified word identity**: progress is stored per *(user, track, normalised term)* in `UserWord`, so built-in words, deck cards and scanned pairs with the same term share one Leitner box and appear once in the lists.
- **Lists actions**: "move to Learned" sets box 5; "move to Missed" sets box 1 with at least one miss; "move to Want" sets the flag. Deleting from Learned or Missed resets the progress. Deleting from Want clears the flag. A row with no flag and no progress is removed.
- **Level unlock**: a level is unlocked when the previous level is ≥ 70% learned (box 5). A1 is always open. The user's CEFR level per track is a self-reported profile setting and does not lock content.
- **Definition mode on decks**: deck cards only enter the Match Game if they have a definition, because Uzbek is never allowed in definition games.
- **Private decks**: only the owner can open them. The Share button offers to make a deck public first, because the share link must work for others.
- **XP**: points per correct answer per game (match 10, builder/write 8, review/memory 6, falling/learn 5, speed 4, derdiedas 3, flashcards 2), +20% for a perfect session (+50% for a perfect Match round), with a session cap of 400 XP. Level L needs 50·L·(L−1) XP.
- **Streak** day boundary uses `TIME_ZONE` (default Asia/Tashkent).
- **Achievements**: 14 badges (first game/scan/deck, perfect round, 3/7/30-day streak, 10/100/500 learned, 1000 XP, daily player, polyglot, deck master).

## Content
- **Seed**: exactly 60 words per level per language (600 total), 4 themed packs of 15 words. Written by hand in pipe-separated text files (`backend/words/seed/*.txt`), loaded idempotently by `manage.py seed_words`, which validates ≥ 60 words per level.
- German nouns are written with their article in the seed and stored as `article` + `word`. Plural-only nouns (e.g. *die Kopfschmerzen*, *die Schulden*) are stored with *die*.
- Uzbek uses Latin script with ASCII apostrophes (o', g').
- English verbs are listed as "to …". Answer checking ignores a leading "to" / article.

## Auth & Telegram
- `email` is optional on the custom User (Telegram-only accounts). Login is by email + password, the Telegram Login Widget, or Mini App `initData`.
- **Linking**: a logged-in web user can link Telegram (widget or initData). If a Telegram-only account already exists, it is **merged** into the web account: words keep the higher box, and decks, sets, sessions, activity, badges and XP are moved over. A Telegram-only user can add an email + password from the profile.
- In the Mini App the client **always** re-authenticates with `initData`, so the identity can't go stale.
- **Mock Telegram login** (unsigned initData / widget data) only works when `DEBUG=true` *and* there is no bot token. It is never allowed in production.
- `initData` max age: 24h (`TELEGRAM_AUTH_MAX_AGE`).
- Bot ↔ backend uses a small internal API protected by the `X-Bot-Secret` header, instead of giving the bot DB access.
- Reminders: the bot polls `/api/games/bot/reminders-due/?mark=1` every minute. A user gets at most one reminder per day, only if they haven't played that day.

## OCR
- Model `claude-opus-5-5` (configurable), structured outputs (`output_config.format` with a JSON schema), `effort: low`, server-side refusal fallback enabled (`fallbacks: "default"`). Validation is still done in our own code (`ocr/schema.py`), with one retry on invalid JSON.
- Images are re-encoded to JPEG ≤ 1600px on the client **and** the server. They are kept only in memory and never written to storage (`ScanLog` stores counts only).
- Rate limit: 20 scans per user per local day. Upload limit 10 MB (413 above that).
- If the detected language differs from the active track, the review screen warns and saves the set under the detected language.

## Frontend
- One SPA serves both the website and the Mini App. Telegram is detected by the presence of `initData`.
- State: zustand. Routing: react-router. i18n: plain JSON + a tiny `t()`, with a test that fails if any key is missing in uz/en/ru.
- Sounds are synthesized with WebAudio (no audio files). Confetti: `canvas-confetti`. TTS: Web Speech API (`en-US` / `de-DE` voice).
- English track tint = violet, German track tint = warm yellow (`data-track` on `<html>`).
- Card back colours: word cards use the track tint, definition cards a lighter violet.
- Telegram: BackButton on inner pages, MainButton on the setup/scan/review screens, HapticFeedback on match and miss, theme from `themeParams`.

## Infra
- Docker Compose: Postgres 16, backend (gunicorn + whitenoise; the entrypoint waits for the DB, migrates, seeds, creates the admin, collects static), frontend (nginx serving the build and proxying `/api`, `/admin`, `/static`, `/media`), bot (`restart: on-failure`; exits 0 without a token).
- Render: Postgres + Docker web service + static site with rewrites to the API (same origin, no CORS) + Docker worker for the bot.
- Local dev uses SQLite.
