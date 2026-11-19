# Yodflip 🃏

Vocabulary games for Uzbek-speaking learners of **English** and **German**, as a responsive website **and** a Telegram Mini App. Both share one backend and one account system.

> 🇺🇿 [O'zbekcha qo'llanma pastda](#-ozbekcha)

- 📸 **Photo → game**: snap a vocabulary page, review the extracted word–definition pairs, play the Match Game.
- 🃏 **Match Game**: words on top, same-language definitions at the bottom, 3D flips, rounds of 4–8 pairs.
- 📚 **Built-in levels** A1–C1 for each language: 600 words with definitions, Uzbek translations and examples, grouped into themed packs, with a 70% unlock rule.
- 🗂️ **My Decks** (Quizlet-style): bulk paste, CSV import/export, share links, Flashcards / Learn / Write, TTS.
- 🎮 **Memorization games** (word ↔ Uzbek): Speed Match, Word Builder, Falling Words, Memory Pairs (extra game), Der·Die·Das (German only), Review (Leitner), Daily Challenge with a global leaderboard.
- 🔥 XP, levels, streaks, 14 badges, weekly and all-time leaderboards. UI in Uzbek (default), English and Russian. Light and dark themes, plus Telegram theme colours.

## Quick start (Docker)

```bash
cp .env.example .env        # optional, everything works without keys
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | the app (website and Mini App) |
| http://localhost:8080/api/docs/ | Swagger API docs |
| http://localhost:8080/admin/ | Django admin (`admin@wordflip.local` / `admin12345`, change via env) |

Migrations, the 600-word seed and the admin user are applied automatically on start (`backend/entrypoint.sh`).
Requires Docker Compose ≥ 2.24 (for the optional `.env` file).

### MOCK mode (no keys needed)

| Missing key | Behaviour |
|---|---|
| `ANTHROPIC_API_KEY` | Scans return realistic sample pairs (EN or DE, depending on the active track) |
| `TELEGRAM_BOT_TOKEN` | The bot container exits cleanly; with `DEBUG=true` the login page shows **“Continue with Telegram (demo)”** (unsigned initData accepted, dev only) |

With `OCR_MOCK=false` and no Anthropic key, OCR falls back to **Tesseract** plus a heuristic parser (Tesseract is installed in the backend image).

## Local development without Docker

```bash
# backend (Python 3.12). Local dev needs DEBUG=true: `cp .env.example .env` (it has DEBUG=true)
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt          # tests use config.test_settings (no .env needed)
python manage.py migrate && python manage.py seed_words
python manage.py runserver                          # http://localhost:8000

# frontend (Node 20+)
cd frontend
npm install
npm run dev                                         # http://localhost:5173 (proxies /api to :8000)

# bot (optional)
cd bot && pip install -r requirements.txt
TELEGRAM_BOT_TOKEN=... WEBAPP_URL=https://... python main.py
```

### Tests and lint

```bash
cd backend  && pytest && ruff check .
cd frontend && npm test && npm run lint && npm run build
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev key | Django secret (**set in production**) |
| `DEBUG` | `true` | Django debug. Mock Telegram login is only possible when `true` |
| `DATABASE_URL` | SQLite | Postgres URL, e.g. `postgres://user:pass@host:5432/db` |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | | Standard Django hosts / origins |
| `ANTHROPIC_API_KEY` | – | Claude vision OCR. Empty → mock |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Model for extraction |
| `OCR_MOCK` | auto | Force mock on/off |
| `OCR_DAILY_LIMIT` | `20` | Scans per user per day |
| `TELEGRAM_BOT_TOKEN` | – | Bot token (also used to verify initData / Login Widget) |
| `TELEGRAM_BOT_USERNAME` | – | Bot username without `@`, enables the Login Widget on the site |
| `WEBAPP_URL` | `http://localhost:8080` | Public **HTTPS** URL of the frontend (Mini App URL) |
| `BOT_API_SECRET` | dev secret | Shared secret between bot and backend (`X-Bot-Secret`) |
| `DJANGO_SUPERUSER_EMAIL` / `_PASSWORD` | – | Admin user created on start |
| `TIME_ZONE` | `Asia/Tashkent` | Day boundary for streaks, daily challenge and reminders |

## Creating the Telegram bot (@BotFather)

1. Open [@BotFather](https://t.me/BotFather) → `/newbot` → choose a name and a username. Copy the **token** into `TELEGRAM_BOT_TOKEN`, and the username (without `@`) into `TELEGRAM_BOT_USERNAME`.
2. **Mini App URL**: `/mybots` → your bot → *Bot Settings* → *Configure Mini App* → *Enable Mini App* → paste your public HTTPS frontend URL (e.g. `https://wordflip-web.onrender.com`). The bot also sets a **“Play”** menu button to `WEBAPP_URL` on start.
3. **Login Widget for the website**: `/setdomain` → choose the bot → send your website domain (e.g. `wordflip-web.onrender.com`).
4. Commands are registered automatically on start: `/start`, `/daily`, `/stats`, `/review`, `/remind 19:00|off`.

Telegram requires **HTTPS** for Mini Apps. For local testing, expose port 8080 with a tunnel (e.g. `cloudflared tunnel --url http://localhost:8080` or `ngrok http 8080`) and use that URL as `WEBAPP_URL`.

## Deploying to production (Render)

See **[DEPLOY.md](DEPLOY.md)** (English + Uzbek): Render Blueprint, env vars, @BotFather setup (`/setmenubutton`, Mini App URL) and how to update.
Production-like run locally: `docker compose -f docker-compose.prod.yml up --build` → http://localhost:8000

## Architecture

```
backend/   Django 5 + DRF + SimpleJWT + drf-spectacular
  accounts/       custom User (email optional, telegram_id), register/login/me, account merge
  telegram_auth/  initData + Login Widget HMAC verification, linking
  words/          Pack, Word (definition + Uzbek), UserWord (Leitner box + 3 lists), seed files
  decks/          Deck, Card, WordSet (scans), bulk parser, CSV, sharing
  games/          Game Direction Rules, word sources, scoring, results, daily challenge, bot API
  ocr/            Claude vision → strict JSON (validated, 1 retry) → Tesseract fallback → mock
  gamification/   XP/levels, streaks, achievements, leaderboards, profile stats
frontend/  React + Vite + TS + Tailwind + Framer Motion (one SPA for web and Mini App)
  src/games/      matchMachine.ts (pure state machine), direction.ts (rules), 8 game components
bot/       aiogram 3 bot with Web App buttons and daily reminders
```

---

## 🇺🇿 O'zbekcha

**Yodflip** — ingliz va nemis tillarini o'rganayotgan o'zbek tilli foydalanuvchilar uchun so'z o'yinlari. U veb-sayt va Telegram Mini App sifatida ishlaydi. Ikkalasida backend ham, hisob ham bitta.

- 📸 **Rasm → o'yin**: lug'at sahifasini suratga oling, topilgan so'z–ta'rif juftlarini tekshiring va juftlash o'yinini o'ynang.
- 🃏 **Juftlash o'yini**: tepada so'zlar, pastda o'sha tildagi ta'riflar, 3D aylanuvchi kartalar.
- 📚 **Ichki darajalar** (A1–C1): har bir til uchun 300 tadan, jami 600 so'z. Har birida ta'rif, o'zbekcha tarjima va misol bor. Keyingi daraja 70% o'zlashtirilganda ochiladi.
- 🗂️ **To'plamlar** (Quizlet uslubida), 🎮 **yodlash o'yinlari** (so'z ↔ o'zbekcha), 🔥 XP, seriya, nishonlar va reyting.

### Ishga tushirish (Docker)

```bash
cp .env.example .env        # ixtiyoriy: kalitlarsiz ham ishlaydi
docker compose up --build
```

- Ilova: http://localhost:8080
- API hujjatlari: http://localhost:8080/api/docs/
- Admin: http://localhost:8080/admin/ (`admin@wordflip.local` / `admin12345`)

Migratsiyalar, 600 so'zlik baza va admin foydalanuvchi ishga tushishda avtomatik yuklanadi.

**MOCK rejim:** `ANTHROPIC_API_KEY` bo'lmasa, skaner namuna so'zlarni qaytaradi. `TELEGRAM_BOT_TOKEN` bo'lmasa, bot ishga tushmaydi va kirish sahifasida “Telegram orqali davom etish (demo)” tugmasi chiqadi (faqat `DEBUG=true` da).

### Muhit o'zgaruvchilari

Asosiylari: `SECRET_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `WEBAPP_URL`, `BOT_API_SECRET`. To'liq ro'yxat yuqoridagi jadvalda va `.env.example` faylida.

### @BotFather orqali bot yaratish

1. [@BotFather](https://t.me/BotFather) → `/newbot` → nom va username tanlang. Tokenni `TELEGRAM_BOT_TOKEN` ga, username'ni (`@` siz) `TELEGRAM_BOT_USERNAME` ga yozing.
2. **Mini App manzili:** `/mybots` → botingiz → *Bot Settings* → *Configure Mini App* → *Enable Mini App* → frontendning HTTPS manzilini kiriting (masalan `https://wordflip-web.onrender.com`).
3. **Saytdagi Telegram Login Widget:** `/setdomain` → botni tanlang → sayt domenini yuboring.
4. Bot buyruqlari avtomatik o'rnatiladi: `/start`, `/daily`, `/stats`, `/review`, `/remind 19:00` (o'chirish: `/remind off`).

Telegram Mini App faqat **HTTPS** bilan ishlaydi. Lokal sinov uchun `cloudflared tunnel --url http://localhost:8080` yoki `ngrok http 8080` dan foydalaning.

### Render'ga joylash

Batafsil qo'llanma: **[DEPLOY.md](DEPLOY.md)**.

### Testlar

```bash
cd backend  && pytest && ruff check .
cd frontend && npm test && npm run lint
```
