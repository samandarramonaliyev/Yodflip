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
- **Level unlock**: see *Level progress* below (found words, server-side). A1 is always open. The user's CEFR level per track is a self-reported profile setting and does not lock content.
- **Definition mode on decks**: deck cards only enter the Match Game if they have a definition, because Uzbek is never allowed in definition games.
- **Private decks**: only the owner can open them. The Share button offers to make a deck public first, because the share link must work for others.
- **XP**: points per correct answer per game (match 10, builder/write 8, review/memory 6, falling/learn 5, speed 4, derdiedas 3, flashcards 2), +20% for a perfect session (+50% for a perfect Match round), with a session cap of 400 XP. Level L needs 50·L·(L−1) XP.
- **Streak** day boundary uses `TIME_ZONE` (default Asia/Tashkent).
- **Achievements**: 14 badges (first game/scan/deck, perfect round, 3/7/30-day streak, 10/100/500 learned, 1000 XP, daily player, polyglot, deck master).

## Content
- **Seed**: exactly A1 100 / A2 150 / B1 200 / B2 250 / C1 300 words per track (2000 total), in themed packs of 15–20. Written by hand in pipe-separated text files (`backend/words/seed/*.txt`), validated by `manage.py check_seed` and loaded idempotently by `manage.py seed_words`. Words are matched by *(track, word, article)*, so existing words keep their IDs; the seed never deletes words. Multi-word expressions (e.g. *post office*, *in der Nähe*) are allowed as one entry.
- **One level per word**: `Word` is unique per *(track, word, article)*. The only existing clash, DE *das Angebot* (A2 "offer" and B2 "supply"), was resolved by renaming the B2 row in place to *der Engpass* (same ID).
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

## Reminder cron URL (fix: 403 with a correct-looking secret)
- **Cause:** the cron URL expected `sha256("yodflip-cron:" + BOT_CRON_SECRET)[:40]`, not `BOT_CRON_SECRET` itself, so a URL containing the env var's value always got 403. Also, the route required a trailing slash and only matched secrets without `/`.
- **Now:** `/bot/cron/<BOT_CRON_SECRET>/` (whitespace stripped, trailing slash optional, `/` and `+` allowed, GET or POST, CSRF-exempt, no auth or throttling), compared with `hmac.compare_digest`. The older derived form is still accepted, so a link set up earlier keeps working. Without `BOT_CRON_SECRET`, a value derived from `SECRET_KEY` is used (shown by `manage.py telegram_setup`).
- A 403 is logged as `Cron 403: secret mismatch (given length, whether BOT_CRON_SECRET is set, expected length, client IP)`, never the secret. `core.logging.RedactSecretsFilter` (Django logs, e.g. `django.request` "Forbidden: …") and a redacting gunicorn access logger replace `/bot/cron/<secret>` and `/bot/webhook/<secret>` with `<redacted>`.

## Level progress (found = learned)
- Progress lives in `UserLevelWord` (one row per user and built-in word): `found_at`, `filler_uses` (0–2), `last_shown_at`. Level progress = found rows / words in the level, computed in SQL on every request; client counters are never trusted.
- **Unlock** at `ceil(70% × total)` found words of the previous level: A1 70, A2 105, B1 140, B2 175 (C1 210 only matters for completion).
- **Rounds** are built by the server (`GET /api/levels/{track}/{level}/round/?size=N&game=&pack=`) and stored as `LevelRound` (the `session_id`), with the shown word IDs and filler IDs, so answers are validated server-side (a client can't mark a word as a filler or answer words that weren't shown).
- "Last 2 sessions" = the user's last 2 rounds of the same track and level. Their words go to the back of the queue; they are not excluded (when few unfound words remain they still appear).
- Round size is clamped to 3–60. If fewer words are available (even with fillers) the round is simply smaller; 1–2 word rounds are allowed when only 1–2 unfound words remain (better than blocking the last words of a level).
- **Fillers**: only when the unfound pool can't fill the board. `filler_uses` grows on the first answer to that filler in a round (idempotent per round via `LevelAnswer`), not when it's shown, so a refreshed or abandoned round doesn't burn uses. Fillers give no XP, change no list and no progress.
- **Pack filter / Der·Die·Das**: the pool is the pack (or the nouns for Der·Die·Das). When that pool has no unfound words, the API returns `pool_done` (the level isn't complete yet) and the app suggests another pack.
- `POST /api/levels/answer/` takes one answer (`{session_id, word_id, correct}`) or a batch (`{session_id, answers: [...]}`); the app sends one batch per finished round. Idempotency: `found_at` is set with a conditional `UPDATE … WHERE found_at IS NULL`, `LevelAnswer` is unique per (round, word), `LevelCompletion` per (user, track, level).
- **XP** in level games: base XP per *newly found* word (game rate) + perfect-round bonus, paid once per round (`LevelRound.xp_awarded`). `/api/games/results/` with `source=level` requires the `session_id` and re-applies the answers idempotently, so a lost `/answer/` call doesn't lose progress.
- **Lists**: a found word is set to Learned (box 5) in `UserWord`, which also removes it from Missed. A miss on an unfound word puts it in Missed (box 1). A level miss never demotes a word that is already Learned (e.g. from a deck). Removing a word from the Learned list does not undo level progress (found is permanent).
- **Completion** (100%): +200 XP and the `level_complete` badge (🎓), exactly once. The completion screen links to the next level and to a review session (`source=levelreview`: the found words of that level, played as a normal Leitner review, no level progress).
- **Migration**: `words/0002_level_progress` converts Leitner box-5 progress on built-in words (by word FK or normalised term) into found rows. `seed_words` runs the same backfill after loading new words, so terms a user learned from decks that are now built-in level words count too.
- Decks, scanned sets and lists keep the Leitner boxes; only level progress moved to found words.

## Scanner camera
- "📷 Kameradan olish" opens an in-app camera (`getUserMedia`, back camera, ideal 1920×1080) with a page frame, shutter, torch (only if the track reports `torch` capability), camera switch (only with > 1 video input) and close. The photo is drawn to a canvas, scaled to ≤ 1600px and encoded as JPEG 0.85; "Ishlatish" sends it straight to OCR.
- Fallbacks: no `getUserMedia` / insecure context → `<input capture="environment">` immediately plus the permission hint; any getUserMedia error → an error screen (denied / not found / busy / unsupported, in Uzbek) with "use the phone camera app" (`<input capture>`), "gallery" and "retry". All tracks are stopped on close, on "Ishlatish", on unmount and on `pagehide`.
- `Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=(), usb=()` on every response. In Telegram Web the Mini App is an iframe whose `allow` attribute is set by Telegram, which we can't change; mobile Telegram apps open the page directly in a WebView.

## Translation language (picker before memorization games)
- **Pairs**: EN words → uz / ru / de; DE words → uz / ru / en. Never into the word's own language. The API validates `translation_lang` + `direction` (`forward|reverse`) on `/api/games/words/`, `/api/levels/{track}/{level}/round/` and `/api/games/results/` and answers **400** for en→en, de→de, unknown codes or directions. Default when omitted: Uzbek, forward.
- **Data**: `WordTranslation(word, lang, text, example_translation)`, unique (word, lang). Migration `words/0003` copies every existing Uzbek text into it (lang = uz); `Word.translation_uz` is kept for compatibility. ru + the other language live in `backend/words/seed/translations/{track}_{level}.txt` (`word | ru | example_ru | de-or-en | example`); Uzbek stays in the main files. The seed upserts translations (files are the source of truth) and only runs when any seed file changed.
- **Check** (`manage.py check_seed`): every word has uz + ru + the other language, each with an example translation; none is empty or an exact copy of the word. A cognate that differs by an article (*baby → das Baby*) counts as a real translation; exact copies got a second natural alternative (*modern → modern, zeitgemäß*, *bank → bank, moliya muassasasi*).
- **Picker**: shown before Speed Match, Word Builder, Falling Words, Memory, Review, Daily and level games in memorization mode. Never for Match (definition game), Der·Die·Das, or deck games (decks use their own language; the reverse toggle stays in the game setup). Deck study modes (Flashcards / Learn / Write) use the deck language too, so they have no picker.
- **Remember**: `TranslationPreference` per user and track (`preferred_translation_lang`, `preferred_direction`, `remember_choice`) via `GET/PUT /api/auth/translation-prefs/`, so the website and the Mini App share it. With "Tanlovimni eslab qol" the game starts directly. The header chip (e.g. `EN → RU ▾`) reopens the picker; a new choice changes the URL (`tl`, `dir`), which restarts the round, and is saved (keeping the remember flag as chosen in the picker; the chip opens with it off).
- **Lists / Review**: built-in words get the chosen language from `WordTranslation`. User words without that language (old scanned words in Missed/Want) are left out of that game rather than shown in the wrong language. Results in another language never overwrite the Uzbek text stored in `UserWord`.
- **Progress** belongs to the word: level rounds and found words don't depend on the language (a word found in EN→RU is not offered again in EN→UZ).
- **Daily Challenge**: same 10 words for everyone, each user sees their language; one shared leaderboard.
- **Stats**: `GameSession.translation_lang` (memorization games only) → profile line "O'ynalgan tillar: UZ 60%, RU 30%, DE 10%".
- **Decks**: `Deck.translation_lang` (uz/ru/en/de, ≠ track, default uz) is chosen at creation; cards are written in it. Optional `Card.extra_translations` ({lang: text}). "AI bilan tarjima qilish" (`POST /api/decks/{id}/translate/ {lang}`) fills missing languages with Claude and caches them on the cards; without an API key (or on an API error) it answers 503 and the app greys the button out ("Tarjima mavjud emas"). Copying a shared deck or turning a set into a deck keeps the languages.
- **Scanner**: the same LLM request now also returns `translation_ru` and `translation_alt` (German for English books, English for German books), stored in `SetPair.translations`. The set editor has a language tab switcher (UZ / RU / EN|DE). `available_langs` on a set tells the picker which languages exist; the others are greyed out. Mock mode and the Tesseract fallback generate no new languages.
- **Answer checking**: alternatives split by `,` `/` `;`; case-insensitive and trimmed; Russian ё = е; German ä/ö/ü/ß = ae/oe/ue/ss; a leading der/die/das/the/a/an/to is optional. Typos: 1 edit for 3–6 letters, 2 for longer; answers of 1–2 letters must be exact (otherwise nearly anything would pass).
- **TTS**: the foreign word speaks with its own voice; the translation side has a speaker button in the chosen language only when the device has that voice (Uzbek is usually missing, so the button is hidden).
- The interface language (uz/ru/en) is a separate setting and is not changed by the picker.

## Two-sided flashcards ("Topdim / Topa olmadim")
- New game **Kartochkalar** (`/play/flashcards?source=…`) for levels, decks, scanned sets and the Want / Missed lists. The deck page's "Kartochkalar" button and the profile's "Bu ro'yxatni o'rganish" open it.
- Front = translation in the chosen language (picker from the previous task; decks use their own language), back = the foreign word (German article coloured: der blue, die red, das green), part of speech, example, 🔊. The picker's direction does not change flashcards: the front is always the translation, the header toggle "Teskari" swaps it.
- Answer buttons (and swipe / ←→ keys) work only after the current card was flipped once; Space flips.
- Every answer is saved immediately: `POST /api/words/flash/answer/` with a client-generated `client_id` (retries return the same result). Topdim → Learned (box 5), removed from Want / Missed; built-in word → level "found" once (`mark_found`, completion bonus via the shared `check_completion`). Topa olmadim → Want-to-learn, removed from Learned (box back to 1; the miss counter is unchanged, so it is not added to Missed). Never reduces level progress.
- Undo (`POST /api/words/flash/undo/`) restores the stored snapshot of the list row (or deletes the row if the answer created it), the deck card status, and removes the level "found" mark if that answer set it. It is meant for the latest answer.
- Deck cards: `Card.study_status` known / learning, only for the deck owner's answers; the deck API returns `known_count` / `learning_count`.
- Results of a flashcards session give flashcards XP but do not touch the lists again (no Leitner miss → Missed). In level rounds, XP counts only words found in that round.
- End screen: "Topdim N / Topa olmadim M", "Topa olmaganlarni qayta o'rganish" (restarts with the missed cards), "Yangi o'yin", "Bosh sahifa".

## Profile word lists
- Tabs Yodlanganlar · Yodlanadiganlar · Topa olmaganlar with counts. Collapsed: the 6 most recent words + "Hammasini ko'rish (N)". Expanded: search, sort (newest / A–Z), level and deck filters, 30 rows per request ("Ko'proq yuklash"), move / delete / 🔊 per row, "Yopish" at the top and sticky at the bottom on mobile (collapsing scrolls to the section header).
- Backend: `GET /api/me/words/?list=&page=&page_size=(max 30)&search=&sort=new|az&level=&deck=&track=` → `count`, `has_more`, `counts` for all three lists, `results`. Deck filter = words whose term is a card of that (own) deck.
- The open/closed state per tab is kept in `sessionStorage` (session only).
