# Decisions & assumptions

Everything that was not fully specified, and what was chosen.

## Product
- **Name**: **Yodflip** ("yod" = memory/remembering in Uzbek + the card flip). Renamed from the working title WordFlip. Infrastructure identifiers (`wordflip` DB/service names in docker-compose and render.yaml, package names, the daily-challenge seed) were kept so existing data and URLs don't change.
- Track labels are plain **EN** / **DE** text instead of flag emoji (Windows renders flag emoji as the letters "GB"/"DE").
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

## End-of-game flow (fix for the stuck Match Game)
- **Root cause**: the Match Game's round-end effect set `finished = true` *before* its 650ms timer and listed `onFinish` (a new function on every parent render) as a dependency. Any re-render during that window cancelled the timer, and the re-run exited early because `finished` was already true, so the round never ended.
- **Fix**: one pure session state machine for every game (`src/games/session.ts`: `playing → round_complete → game_complete`, `RESTART`). The Match round-end timer depends only on `phase`, reads the latest values from refs, and sets `finished` inside the timer. Matched cards fade out (keeping their grid slot) instead of leaving dashed boxes.
- **Saving**: each finished round is posted to `/api/games/results/` exactly once (guarded by `playId + round` in the runner and by the reducer, which accepts `ROUND_DONE` only once per round). That's why the "Round complete" card can show the XP the server confirmed. The final screen shows the sum of all rounds and never re-submits. A player who quits mid-game keeps the progress of the rounds they finished.
- **"Yangi o'yin"**: same word set, reshuffled locally, from round 1 (a new `playId`, so nothing is saved twice). **"Boshqa to'plam"** goes to the level page, the scans list, the deck, or the word list the game came from. The Daily Challenge and Review only show "Yangi o'yin" and "Bosh sahifa" (a Daily replay is practice and earns no XP).

## Production (Render)
- **One web service serves the React build and the API.** Same origin for the site, the API and the Telegram Mini App, so there's no CORS, no proxy rules and one URL for @BotFather. Whitenoise serves `/assets/*` (hashed, `immutable`) and the build root. `core.views.spa` returns `index.html` for client routes with `frame-ancestors` allowing `web.telegram.org`, because Telegram Web shows Mini Apps in an iframe. Everything else keeps `X-Frame-Options: DENY`. `/api/`, `/admin/`, `/static/`, `/media/` and `/assets/` are never answered with `index.html` (a missing asset is a 404, not HTML).
- **The bot is a Render web service, not a worker:** webhook mode needs a public HTTPS URL, which workers don't have. It sets its webhook on every start (`RENDER_EXTERNAL_URL/telegram/webhook`) with a `secret_token` derived (sha256 hex) from `WEBHOOK_SECRET`, because Telegram only accepts `[A-Za-z0-9_-]` and Render's generated values are base64. Without a public URL it falls back to polling (local).
- **Settings fail closed:** with `DEBUG=false`, a missing `SECRET_KEY`, `ALLOWED_HOSTS`, `DATABASE_URL` or `BOT_API_SECRET` (≥ 16 chars), or a SQLite URL, raises `ImproperlyConfigured`. Render's `RENDER_EXTERNAL_HOSTNAME`/`URL` are added to `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` automatically. `DEBUG` now defaults to **false**; local dev sets `DEBUG=true` in `.env`, and tests use `config.test_settings`.
- **HTTPS:** `SECURE_SSL_REDIRECT` (health check exempt), secure session/CSRF cookies, HSTS 1 year. `includeSubDomains`/`preload` are off by default, because they would pin HTTPS for subdomains of a domain we may not own (`*.onrender.com`); both are configurable, and their deploy checks are silenced with that reason. `manage.py check --deploy` reports no issues.
- **Media in PostgreSQL** (`core.StoredFile` + `core.storage.DatabaseStorage`), because Render container disks are ephemeral and an S3 bucket would be one more account to manage. Card images are re-encoded to JPEG ≤ 800px (EXIF stripped, ≤ 2 MB) and served from `/media/<uuid>.jpg` with immutable caching. Scan photos are still never stored.
- **Seed once:** `seed_words` stores a sha256 of the seed files in `core.SeedState` and skips when unchanged (`--force` reloads).
- **OCR in production without an Anthropic key uses Tesseract**, not sample data. Mock OCR is a DEBUG-only default (and can still be forced with `OCR_MOCK=true`, as in the local prod smoke test).
- **Free plans in render.yaml** so nothing is billed by surprise. DEPLOY.md explains the sleep and 30-day DB expiry and recommends starter + basic-256mb for real users.
- **gunicorn** with 2 workers × 4 threads (fits 512 MB), access log to stdout. The container runs as a non-root user.

## Single-service deployment (supersedes the multi-service Render setup above)
- **One Render web service** (native Python runtime, free plan). `build.sh` installs Python deps, builds React (`npm ci && npm run build`), runs `collectstatic`, `migrate`, `seed_words` (skipped when the seed hash is unchanged) and `ensure_superuser`. Start: `gunicorn -c gunicorn.conf.py`. If the runtime has no Node ≥ 18, `build.sh` downloads Node 20 into `.render/node`.
- Migrations run **during the build**, because Neon is reachable from Render's build environment and the free plan has no pre-deploy hook. Seeding is idempotent and hash-guarded, so rebuilds are cheap.
- **The frontend uses relative `/api/...` URLs only** (`VITE_API_URL` and `django-cors-headers` were removed): one origin in production (Django serves the build) and in development (Vite proxy).
- **The Telegram bot runs inside Django** (`telegram_bot` app, aiogram 3). `POST /bot/webhook/<secret>/` checks both the path secret and Telegram's `X-Telegram-Bot-Api-Secret-Token`, then dispatches the update with `async_to_sync`. Handlers use the ORM through thread-sensitive `sync_to_async`, so they run on the request's own DB connection. It always returns 200 (after logging errors) so Telegram doesn't retry a broken update forever. The separate bot service, its internal HTTP API (`games/bot_views.py`, `BOT_API_SECRET`) and the `bot/` folder were removed.
- **Webhook registration on startup:** gunicorn's `when_ready` hook (master process, once per start, including every wake-up on the free plan) calls `setWebhook` (with `secret_token`), `setMyCommands` and `setChatMenuButton` (web_app = `PUBLIC_URL`). It never blocks startup on failure. `manage.py telegram_setup` does the same by hand and prints the cron URL.
- **Reminders without a worker:** `GET/POST /bot/cron/<secret>/` sends due reminders (each user at most once per day). An external free scheduler (cron-job.org, every 10 min) calls it, which also keeps the free service awake.
- **Neon:** the connection string is used as-is (`?sslmode=require`). For the pooled `-pooler` endpoint (PgBouncer, transaction mode) server-side cursors are disabled automatically.
- **OCR on Render:** the native runtime has no Tesseract, so photo scanning in production needs `ANTHROPIC_API_KEY`. Without it, a scan returns a friendly "couldn't read the page" error instead of sample data. The optional Docker image still includes Tesseract.
- Docker is now optional (`Dockerfile` + `docker-compose.yml` = the same single service + Postgres, for local production-like runs). The per-app Dockerfiles, nginx config and `docker-compose.prod.yml` were removed.
