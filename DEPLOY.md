# Deploying Yodflip: one Render web service + Neon PostgreSQL

> 🇺🇿 [O'zbekcha qo'llanma pastda](#-ozbekcha)

## How it works

```
                 https://yodflip.onrender.com   (one Render web service, free plan)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ gunicorn → Django                                                    │
 │   /api/...                REST API                                   │
 │   /bot/webhook/<secret>/  Telegram bot (aiogram 3, webhook mode)     │
 │   /bot/cron/<secret>/quiz/ in-chat quiz (called EVERY HOUR by cron)  │
 │   /bot/cron/<secret>/     daily reminders (called by a free cron)    │
 │   /assets/..., /...       React app (whitenoise; index.html for SPA) │
 └───────────────────────────────┬──────────────────────────────────────┘
                                 │ DATABASE_URL (SSL)
                       Neon PostgreSQL (free)
```

- **Build** (`build.sh`): `pip install` → `npm ci && npm run build` → `collectstatic` → `migrate` (includes the level-progress data migration) → `check_seed` (fails the build on a broken vocabulary file) → `seed_words` (only when the seed files changed; idempotent, keeps word IDs, never deletes) → `check_exams` + `seed_exams` (the exam packs, same rules) → admin user. Nothing has to be run by hand.
- **Start:** `gunicorn`. On startup it registers the Telegram webhook, the bot commands and the "Play" menu button (Mini App) automatically.
- The frontend calls the API with relative URLs (`/api/...`): one origin, no CORS.
- Card images are stored in PostgreSQL (Render's disk is temporary).

## 1. Create the database on Neon (free)

1. Sign up at [neon.tech](https://neon.tech) → **New project** → region close to your users (e.g. *Europe (Frankfurt)*) → PostgreSQL 16+.
2. **Dashboard → Connection string**: copy the URL. It looks like
   `postgresql://user:password@ep-xxxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`
   Keep `?sslmode=require`. The pooled (`-pooler`) URL is recommended; the app adjusts for it automatically.

## 2. Create the Telegram bot

[@BotFather](https://t.me/BotFather) → `/newbot` → name → username (ending in `bot`). Copy the **token**.

## 3. Create the Render service

1. Push the repository to GitHub.
2. Render → **New → Blueprint** → choose the repo. Render reads `render.yaml` (one web service: `yodflip`).
3. Fill in the values Render asks for:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string |
   | `TELEGRAM_BOT_TOKEN` | token from @BotFather |
   | `TELEGRAM_BOT_USERNAME` | bot username without `@` |
   | `TELEGRAM_APP_SHORT_NAME` | short name of the Mini App from @BotFather `/newapp` (see step 4). May stay empty: duel links then open the bot first |
   | `ANTHROPIC_API_KEY` | Claude API key: **needed for photo scanning** (the native Render runtime has no Tesseract) |
   | `DJANGO_SUPERUSER_EMAIL` / `DJANGO_SUPERUSER_PASSWORD` | your admin login for `/admin/` |

   Generated automatically: `SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET`, `BOT_CRON_SECRET`. Render's own hostname fills `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the public URL.
4. **Apply.** The first build takes ~3–6 min. Check `https://<your-service>.onrender.com/api/health/`, which should return `{"ok": true, "db": true, ...}`.
5. In the logs you should see `Telegram webhook set to https://…/bot/webhook/<secret>/`.

## 4. Connect the Mini App in @BotFather

The bot sets its menu button automatically on startup. To set it by hand, or to change the title:

- `/setmenubutton` → choose the bot → send `https://<your-service>.onrender.com` → send the button title, e.g. `O'ynash`.
- `/mybots` → bot → **Bot Settings → Configure Mini App → Enable Mini App** → the same URL.
- Website login with Telegram: `/setdomain` → bot → `<your-service>.onrender.com`.

- **Duel links (`startapp`)**: `/newapp` → choose the bot → title, description, a 640×360 picture → **Web App URL** `https://<your-service>.onrender.com` → **short name**, e.g. `play`. Put that short name into Render's `TELEGRAM_APP_SHORT_NAME`. Duel links then look like `https://t.me/<bot>/play?startapp=duel_<code>` and open the duel directly. Without it the app shares `https://t.me/<bot>?start=duel_<code>` (one extra tap in the bot).

Test: send `/start` to the bot → **🎮 O'yinni ochish**. You're signed in automatically (the server verifies Telegram's `initData` signature with your bot token).

## 5. Bot quiz, daily reminders + keeping the free service awake

There's no background worker, so messages are sent when a secret URL is called.

### 5a. Bot quiz: EVERY HOUR (new, required)

At [cron-job.org](https://cron-job.org) create (or change your existing) cronjob:

| Setting | Value |
|---|---|
| URL | `https://<your-service>.onrender.com/bot/cron/<BOT_CRON_SECRET>/quiz/` (e.g. `https://yodflip.onrender.com/bot/cron/<BOT_CRON_SECRET>/quiz/`) |
| Schedule | crontab `0 * * * *` (every hour, minute 0) |
| Timezone | `Asia/Tashkent` |

It must run every hour: each user chooses an hour in their own timezone, and the call sends the quiz only to users whose hour is now and who haven't played today. Calling it more often is safe (one quiz per user per day). The answer shows the numbers, e.g. `{"ok": true, "due": 12, "sent": 11, "blocked": 1, ...}`. If `remaining` is above 0 (more than ~600 users in one hour), also run it at minutes 5 and 10 (`0,5,10 * * * *`).
A sleeping free service needs 30–60 s to wake up and cron-job.org may report a timeout for that call. Keep the 10-minute job below as well: it keeps the service awake, so the hourly call is on time.

### 5b. Reminders and keep-awake: every 10 minutes

1. Your reminder URL is `https://<your-service>.onrender.com/bot/cron/<BOT_CRON_SECRET>/`, using the
   value of the `BOT_CRON_SECRET` env var (Render → Environment → reveal). You can also set your own
   value there (letters/digits, at least 24 characters). The trailing slash is optional, and GET and POST both work.
   `cd backend && python manage.py telegram_setup` in the Render **Shell** prints the exact URL too.
2. At [cron-job.org](https://cron-job.org) (free): **Create cronjob** → that URL → **every 10 minutes**.
   A correct URL returns `{"ok": true, ...}`. A wrong one returns `403`, and the service log shows
   `Cron 403: secret mismatch (...)` (the secret itself is never logged).

This sends reminders (at most one per user per day, only if they haven't played) and keeps the free service from sleeping. Without it, a free service sleeps after ~15 min idle: the first request then takes 30–60 s, and Telegram retries the webhook, so messages still arrive, just late.

On a day a quiz was sent, the plain reminder is skipped for that user. Both URLs also close duels nobody accepted within 48 hours.

## Updating

- **Code:** `git push`. Render runs `build.sh` again (migrations included) and restarts gunicorn, which re-registers the webhook.
- **Vocabulary:** edit `backend/words/seed/*.txt` and push. It reloads once. Each level must have exactly A1 100 / A2 150 / B1 200 / B2 250 / C1 300 words per track, and every word needs uz + ru + the other track language (`backend/words/seed/translations/`); check locally with `python manage.py check_seed`. To force a reload: `python manage.py seed_words --force` in the Shell (safe: progress is kept).
- **Exam packs:** `backend/exams/seed/<pack>.txt` (+ `seed/extra/ielts-academic.txt` for collocations); check with `python manage.py check_exams`, reload with `python manage.py seed_exams --force`. The lists are original: never paste official word lists.
- **AI deck translation** uses the same `ANTHROPIC_API_KEY` as the scanner; without it the button shows "Tarjima mavjud emas".
- **Camera:** the scanner uses `getUserMedia`, which needs HTTPS (Render provides it). Django sends `Permissions-Policy: camera=(self)`.
- **Env vars:** change them in the dashboard; the service restarts.
- **Rollback:** Render → *Deploys* → pick an earlier deploy → *Rollback*.
- **Custom domain:** Render → Settings → Custom Domains. Then set `ALLOWED_HOSTS=yourdomain.uz`, `CSRF_TRUSTED_ORIGINS=https://yourdomain.uz` and `PUBLIC_URL=https://yourdomain.uz`, redeploy, and update the URLs in @BotFather and cron-job.org.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails with `ImproperlyConfigured` | `DATABASE_URL` (or `SECRET_KEY`) is missing. Production refuses insecure defaults on purpose. |
| Build fails at `migrate` | Check the Neon URL (password, `?sslmode=require`) and that the Neon project is active. |
| Bot doesn't answer | Logs must show `Telegram webhook set to …`. Check `TELEGRAM_BOT_TOKEN`, then run `python manage.py telegram_setup`. |
| Mini App opens but login fails | `TELEGRAM_BOT_TOKEN` must belong to the bot that opened the Mini App. |
| Scanning says it can't read the page | Set `ANTHROPIC_API_KEY`. |
| Quiz buttons do nothing | The webhook must also receive `callback_query`: restart the service (it re-registers the webhook on start) or run `python manage.py telegram_setup`. |
| Duel link opens the bot, not the duel | Create the Mini App with `/newapp` and set `TELEGRAM_APP_SHORT_NAME`. |
| Reminder URL returns 403 | The part after `/bot/cron/` must equal `BOT_CRON_SECRET`. Check the log line `Cron 403: …` (lengths, whether the variable is set). |

---

## 🇺🇿 O'zbekcha

### Qanday ishlaydi

Hammasi **bitta** Render web xizmatida ishlaydi (bepul tarif): Django API, React ilovasi va Telegram bot (webhook rejimida, `/bot/webhook/<secret>/`). Ma'lumotlar bazasi **Neon PostgreSQL** (bepul).

- **Yig'ish** (`build.sh`): `pip install` → `npm ci && npm run build` → `collectstatic` → `migrate` → so'zlar bazasi (faqat fayllar o'zgarganda) → admin foydalanuvchi.
- **Ishga tushirish:** `gunicorn`. U Telegram webhook'ini, buyruqlarni va "Play" tugmasini avtomatik o'rnatadi.

### 1. Neon'da baza yarating

[neon.tech](https://neon.tech) → **New project** → yaqin hududni tanlang (masalan, Frankfurt). **Connection string**ni nusxalang (`?sslmode=require` qismi qolsin).

### 2. Bot yarating

[@BotFather](https://t.me/BotFather) → `/newbot` → nom → username. **Token**ni nusxalang.

### 3. Render xizmatini yarating

1. Kodni GitHub'ga yuklang.
2. Render → **New → Blueprint** → repozitoriyani tanlang.
3. Qiymatlarni kiriting:
   - `DATABASE_URL`: Neon connection string
   - `TELEGRAM_BOT_TOKEN`: bot tokeni
   - `TELEGRAM_BOT_USERNAME`: bot username'i (`@` siz)
   - `ANTHROPIC_API_KEY`: **rasm skanerlash uchun kerak**
   - `DJANGO_SUPERUSER_EMAIL` / `DJANGO_SUPERUSER_PASSWORD`: admin panel uchun login

   `SECRET_KEY`, `TELEGRAM_WEBHOOK_SECRET` va `BOT_CRON_SECRET` avtomatik yaratiladi.
4. **Apply** tugmasini bosing. `https://<xizmat>.onrender.com/api/health/` manzili `{"ok": true, "db": true}` qaytarishi kerak.

### 4. @BotFather'da Mini App

Bot "Play" tugmasini o'zi o'rnatadi. Qo'lda o'rnatish uchun:
- `/setmenubutton` → bot → `https://<xizmat>.onrender.com` → tugma nomi (masalan, `O'ynash`)
- `/mybots` → bot → **Bot Settings → Configure Mini App → Enable Mini App** → o'sha manzil
- Saytda Telegram orqali kirish uchun: `/setdomain` → `<xizmat>.onrender.com`

- **Duel havolalari uchun**: `/newapp` → bot → nom, tavsif, 640×360 rasm → **Web App URL**: `https://<xizmat>.onrender.com` → **short name** (masalan, `play`). Shu nomni Render'da `TELEGRAM_APP_SHORT_NAME` ga yozing. Havola `https://t.me/<bot>/play?startapp=duel_<kod>` ko'rinishida bo'ladi va duelni to'g'ridan-to'g'ri ochadi. Bo'sh qolsa, havola avval botni ochadi.

Sinov: botga `/start` yuboring va **🎮 O'yinni ochish** tugmasini bosing.

### 5. Bot viktorinasi (HAR SOATDA) va eslatmalar

**Viktorina.** cron-job.org da cronjob'ni shunday sozlang:

- URL: `https://<xizmat>.onrender.com/bot/cron/<BOT_CRON_SECRET>/quiz/`
- Jadval (crontab): `0 * * * *` — har soatda
- Vaqt mintaqasi: `Asia/Tashkent`

Har soatda chaqirilishi shart: har bir foydalanuvchi o'z soatini tanlaydi. Ko'proq chaqirish ham xavfsiz — bir kunda bir foydalanuvchiga faqat bitta viktorina boradi.

**Eslatmalar** (avvalgidek, har 10 daqiqada, ikkinchi cronjob sifatida qoldiring — xizmatni "uyg'oq" saqlaydi). Viktorina yuborilgan kuni oddiy eslatma yuborilmaydi.


Eslatma manzili: `https://<xizmat>.onrender.com/bot/cron/<BOT_CRON_SECRET>/`. Bu yerda `BOT_CRON_SECRET` Render → Environment bo'limidagi qiymat (o'zingiz ham kiritishingiz mumkin). Render Shell'da `cd backend && python manage.py telegram_setup` buyrug'i aniq manzilni chiqaradi. [cron-job.org](https://cron-job.org) saytida shu URL'ni **har 10 daqiqada** chaqiradigan cronjob yarating. Bu eslatmalarni yuboradi va bepul xizmatni "uyg'oq" saqlaydi.

### 6. Sifatli talaffuz (Google Cloud Text-to-Speech)

1. [console.cloud.google.com](https://console.cloud.google.com) → **New project** (masalan, `yodflip`). **Billing** ni ulang (bepul oylik limit bor; narx va limitni [rasmiy sahifada](https://cloud.google.com/text-to-speech/pricing) tekshiring). **Billing → Budgets & alerts** da ogohlantirish qo'ying.
2. **APIs & Services → Library** → "Cloud Text-to-Speech API" → **Enable**.
3. **IAM & Admin → Service Accounts → Create** (nom: `tts`, rol kerak emas) → akkaunt → **Keys → Add key → JSON**. Fayl yuklanadi — uni hech kimga bermang, git'ga qo'shmang.
4. Render → **Environment** → `GOOGLE_TTS_CREDENTIALS_JSON` = fayl matnini **to'liq** qo'ying → Save.
5. Audiolarni bir marta tayyorlang (o'z kompyuteringizda; Render bepul tarifida Shell yo'q):
   - `.env` ga `GOOGLE_TTS_CREDENTIALS_JSON='{...bitta qatorda...}'` yozing;
   - `cd backend && python manage.py migrate && python manage.py seed_words && python manage.py seed_exams`
   - `python manage.py generate_tts --dry-run` (nechta fayl va belgi), keyin `python manage.py generate_tts`. To'xtab qolsa, qayta ishga tushiring — davom etadi. Qo'shimcha: `--slow`, `--voices all`, `--lang de`, `--no-examples`.
   - `git add backend/tts_audio && git commit -m "TTS audio" && git push`. (`S3_*` o'rnatilgan bo'lsa, fayllar bucketga yuklanadi va commit kerak emas.)
   - Bu qadam ixtiyoriy: qilinmasa, audio birinchi tinglashda yaratilib, bazada saqlanadi.
6. Tekshirish: `https://<xizmat>.onrender.com/admin/tts-check/` (admin).

Azure: `TTS_PROVIDER=azure`, `AZURE_TTS_KEY`, `AZURE_TTS_REGION`. Kalit bo'lmasa, brauzer ovozi ishlaydi.

### Yangilash

- **Kod:** `git push`. Render `build.sh` ni qayta bajaradi (migratsiyalar ham shu yerda).
- **So'zlar bazasi:** `backend/words/seed/*.txt` ni o'zgartirib push qiling (tekshirish: `python manage.py check_seed`; majburan yuklash: `python manage.py seed_words --force` — progress saqlanadi).
- **Orqaga qaytarish:** Render → *Deploys* → avvalgi deploy → *Rollback*.
