# Deploying Yodflip: one Render web service + Neon PostgreSQL

> 🇺🇿 [O'zbekcha qo'llanma pastda](#-ozbekcha)

## How it works

```
                 https://yodflip.onrender.com   (one Render web service, free plan)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ gunicorn → Django                                                    │
 │   /api/...                REST API                                   │
 │   /bot/webhook/<secret>/  Telegram bot (aiogram 3, webhook mode)     │
 │   /bot/cron/<secret>/     quiz + reminders + scheduled broadcasts    │
 │   /bot/cron/<secret>/status/  what the last runs did (sends nothing) │
 │   /admin/broadcast/       message to the users (staff)               │
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

## 5. Bot quiz, daily reminders, scheduled broadcasts

There is no background worker: messages are sent when one secret URL is called.

### 5a. cron-job.org: exactly ONE cronjob (free plan, required)

| Setting at [cron-job.org](https://cron-job.org) | Value |
|---|---|
| URL | `https://<your-service>.onrender.com/bot/cron/<BOT_CRON_SECRET>/` (for yodflip: `https://yodflip.onrender.com/bot/cron/<BOT_CRON_SECRET>/`) |
| Schedule | crontab `*/10 * * * *` (every 10 minutes) |
| Timezone | `Asia/Tashkent` |
| Request method | `GET` |
| Notifications | on: "execution fails" and "cronjob will be disabled because of too many failures" |

- `<BOT_CRON_SECRET>`: Render → Environment → `BOT_CRON_SECRET` → reveal, copied exactly. Recommended: set your own value of letters and digits only (24+ characters), because a generated value may contain `/`, `+` or `=`.
- This one call does everything: quiz (each user's hour), reminders (each user's `/remind` time), scheduled broadcasts, expired duels. It also keeps the free service awake.
- The old address `/bot/cron/<BOT_CRON_SECRET>/quiz/` runs exactly the same job. An old cronjob may stay or be deleted: nobody gets a message twice.
- Use `https://`, and make sure the cronjob is **enabled** (a service like cron-job.org may disable a job after many failed or timed-out calls, e.g. while a free service was waking up).

Answers: `{"ok": true, "sent": 12, "quiz": {...}, "reminders": {...}}` · `403` = wrong secret · `"detail": "already_running"` = another run is in progress (fine) · `"detail": "bot_disabled"` = `TELEGRAM_BOT_TOKEN` is missing.

### 5b. Check that it works: the status URL

Open `https://<your-service>.onrender.com/bot/cron/<BOT_CRON_SECRET>/status/` in a browser (don't add it as a cronjob: it sends nothing).

| Field | Meaning |
|---|---|
| `minutes_since_last_run` | must stay around 10 or below. `null` or large = cron-job.org isn't calling |
| `users.reminder_enabled` | users who set a reminder time (`/remind 19:00` or profile). **Nobody else gets the plain reminder** |
| `users.bot_blocked` | users the bot can't write to (blocked, or never pressed /start) |
| `jobs.reminders.runs` | the last 7 runs: matched, sent, failed, skipped |
| `skip_reasons` | `reminder_off`, `not_yet_time`, `played_today`, `already_sent_today`, `quiz_sent_today`, `bot_blocked`, `inactive_account`; for the quiz also `quiz_off`, `quiet_day`, `hour_passed` |
| `details.errors` | Telegram's error texts |

The same data is in `/admin/` → **Cron run logs** (kept for 14 days) and, as one line per job, in the Render log (`Job reminders (cron): matched=…`).

**Who gets what:** quiz: on by default at 19:00 (user's timezone), only if the user hasn't played today; a missed hour is made up for during the following 2 hours. Plain reminder: only users with a reminder time, from that time on, at most one a day, and not on a day the quiz was sent.

### 5c. Free or Starter?

| Render plan | Setup |
|---|---|
| **Free** (sleeps after ~15 min) | keep cron-job.org (5a). Leave `ALWAYS_ON_SCHEDULER` empty |
| **Starter ($7, never sleeps)** | set `ALWAYS_ON_SCHEDULER=true`; cron-job.org becomes optional |

With `ALWAYS_ON_SCHEDULER=true` the app runs the same job itself every 10 minutes (`SCHEDULER_EVERY_MINUTES`, 60 = once an hour). A database row lets one gunicorn worker do each run, and cron-job.org may stay on as well: no message is sent twice. Don't set it on the free plan: a sleeping service can't run a timer.

### 5d. Broadcast: `/admin/broadcast/`

`/admin/` → **📣 Xabar yuborish**. Link your Telegram to the admin account first (website → sign in with the admin email → Profile → link Telegram): needed for the test message. Sending runs in the background (≤25 messages / s). After a restart or sleep the broadcast shows "To'xtab qolgan" (up to 2 minutes later): press **Davom ettirish**. Scheduled messages go out with the first cron run after their time (within 10 minutes).

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
| Reminders don't arrive | Open the status URL (5b). `minutes_since_last_run` large → cron-job.org; `matched` 0 → read `skip_reasons`; `failed` → `details.errors`. |
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

### 5. Viktorina, eslatmalar, rejalashtirilgan xabarlar

[cron-job.org](https://cron-job.org) da **bitta** cronjob kerak:

- URL: `https://<xizmat>.onrender.com/bot/cron/<BOT_CRON_SECRET>/` (masalan, `https://yodflip.onrender.com/bot/cron/<BOT_CRON_SECRET>/`)
- Jadval (crontab): `*/10 * * * *` — har 10 daqiqada
- Vaqt mintaqasi: `Asia/Tashkent`, usul: `GET`, xato haqida bildirishnoma: yoqilgan

`BOT_CRON_SECRET`: Render → Environment (aynan o'zini nusxalang; faqat harf va raqamdan iborat 24+ belgili qiymat qo'yish tavsiya etiladi). Bu manzil hammasini bajaradi va bepul xizmatni uyg'oq saqlaydi. Eski `/quiz/` manzili ham xuddi shu ishni bajaradi; ikkalasi birga tursa ham xabar ikki marta ketmaydi.

**Tekshirish:** brauzerda `https://<xizmat>.onrender.com/bot/cron/<BOT_CRON_SECRET>/status/` ni oching. `minutes_since_last_run` 10 atrofida bo'lishi kerak. `skip_reasons` nega yuborilmaganini ko'rsatadi (`reminder_off` = foydalanuvchi vaqt tanlamagan). Oddiy eslatma faqat `/remind 19:00` yoki profilda vaqt tanlaganlarga boradi; viktorina esa hammaga standart bo'yicha 19:00 da boradi (o'sha kuni o'ynamagan bo'lsa).

**Bepul tarif:** cron-job.org qolsin. **Starter ($7):** `ALWAYS_ON_SCHEDULER=true` qo'ying — cron-job.org ixtiyoriy bo'ladi (ikkalasi birga ham xavfsiz).

**Xabar yuborish:** `/admin/` → **📣 Xabar yuborish**. Avval saytda admin email bilan kirib, Profil → Telegram'ni ulang. Shablon yoki matn → "Menga test yuborish" → "Hammaga yuborish" → tasdiqlash. Server o'chib qolsa, 2 daqiqadan keyin **Davom ettirish** tugmasi chiqadi.

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
