# Deploying Yodflip on Render

> 🇺🇿 [O'zbekcha qo'llanma pastda](#-ozbekcha-renderga-joylash)

## Architecture on Render

| Service | Type | What it runs |
|---|---|---|
| `yodflip-web` | Web service (Docker, root `Dockerfile`) | Django + gunicorn **and** the built React app (one URL = website + Mini App + API) |
| `yodflip-bot` | Web service (Docker, `bot/Dockerfile`) | aiogram bot in **webhook** mode + daily reminders |
| `yodflip-db` | Managed PostgreSQL | all data, including uploaded card images |

**Why the React build is served by Django rather than a separate static site:** one origin for the website, the API and the Telegram Mini App. That means no CORS, no proxy rules, one URL to give @BotFather and one service to deploy. Hashed assets are served by whitenoise with `immutable` caching. (The frontend can still be hosted elsewhere: build with `VITE_API_URL=https://<api>` and set `CORS_ALLOWED_ORIGINS`.)

**Why the bot is a web service and not a background worker:** in webhook mode Telegram has to reach the bot over public HTTPS, and Render workers have no public URL. The bot sets its webhook automatically on every start (`RENDER_EXTERNAL_URL` + `/telegram/webhook`, protected by a secret token).

**What happens on each deploy** (`backend/entrypoint.sh`): wait for the DB → `migrate` → `seed_words` (runs only when the seed files changed, otherwise skipped) → create the admin user if missing → start gunicorn. `collectstatic` and the React build run at image build time.

## Costs and plans (decide before you go live)

`render.yaml` uses **free** plans so you can try it at no cost. Free has two catches:
- Free web services **sleep after ~15 minutes** without traffic. The first visit then takes 30–60 s, and the bot's reminders don't run while it sleeps.
- A free PostgreSQL database **expires after 30 days**.

For real users, change to `plan: starter` for both web services and `plan: basic-256mb` for the database (in `render.yaml` or the dashboard).

## Step by step

1. **Create the Telegram bot** (you need the token in step 4):
   [@BotFather](https://t.me/BotFather) → `/newbot` → name → username (must end in `bot`). Copy the **token**.
2. **Push the code to GitHub** (private repos are fine).
3. **Render → New → Blueprint** → connect the repo → Render reads `render.yaml` and shows the three resources.
4. **Fill in the secret env vars** Render asks for (`sync: false`):

   | Service | Variable | Value |
   |---|---|---|
   | yodflip-web | `TELEGRAM_BOT_TOKEN` | the token from @BotFather |
   | yodflip-web | `TELEGRAM_BOT_USERNAME` | bot username without `@` |
   | yodflip-web | `ANTHROPIC_API_KEY` | optional: Claude vision OCR (otherwise Tesseract is used) |
   | yodflip-web | `DJANGO_SUPERUSER_EMAIL` / `DJANGO_SUPERUSER_PASSWORD` | your admin login (`/admin/`) |
   | yodflip-bot | `TELEGRAM_BOT_TOKEN` | the same token |

   Generated automatically: `SECRET_KEY`, `BOT_API_SECRET` (shared with the bot), `WEBHOOK_SECRET`, `DATABASE_URL`. `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` come from Render's own hostname.
5. **Apply.** The first build takes about 5–8 minutes. Then open `https://yodflip-web.onrender.com/api/health/`, which should return `{"ok": true, "db": true, ...}`.
6. **Check the URLs.** If Render gave `yodflip-web` a different hostname (the name was taken), set `WEBAPP_URL` on **yodflip-bot** to the real `https://…onrender.com` URL and redeploy the bot.
7. **Connect the Mini App in @BotFather:**
   - Menu button: `/setmenubutton` → choose your bot → send the URL `https://yodflip-web.onrender.com` → send the button title, e.g. `O'ynash`.
     (The bot also sets this menu button itself on startup, from `WEBAPP_URL`.)
   - Mini App: `/mybots` → bot → **Bot Settings → Configure Mini App → Enable Mini App** → the same URL.
   - Login Widget on the website: `/setdomain` → bot → `yodflip-web.onrender.com`.
8. **Test.** In Telegram, send `/start` to the bot → tap **🎮 O'yinni ochish**. You're signed in automatically: the server verifies Telegram's `initData` signature with your bot token over HTTPS.
9. **Custom domain (optional):** Render → yodflip-web → Settings → Custom Domains. Then add the env vars `ALLOWED_HOSTS=yourdomain.uz`, `CSRF_TRUSTED_ORIGINS=https://yourdomain.uz`, `PUBLIC_URL=https://yourdomain.uz`, set the bot's `WEBAPP_URL` to the new domain, and update `/setdomain` and the Mini App URL in @BotFather.

## Updating after deploy

- **Code:** `git push` to the connected branch. Render rebuilds and redeploys both services (`autoDeploy: true`). Migrations run automatically on start.
- **Vocabulary:** edit `backend/words/seed/*.txt` and push. The seed reloads once because its hash changed. To force a reload: Render Shell → `python manage.py seed_words --force`.
- **Env vars:** change them in the dashboard, and the service restarts.
- **Rollback:** Render → service → *Deploys* → pick an earlier deploy → *Rollback*.
- **Admin:** `https://<your-url>/admin/`.
- **Logs:** Render → service → *Logs*. Bot: look for `Webhook set to …`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails with `ImproperlyConfigured: … must be set` | A required env var is missing (production refuses insecure defaults on purpose). |
| `400 Bad Request` on a custom domain | Add it to `ALLOWED_HOSTS` (and `CSRF_TRUSTED_ORIGINS`). |
| Mini App opens but the login fails | `TELEGRAM_BOT_TOKEN` on **yodflip-web** must be the token of the bot that opened the Mini App. |
| Bot doesn't answer | Bot logs should show `Webhook set to https://…/telegram/webhook`. Check `TELEGRAM_BOT_TOKEN` on yodflip-bot. Free plan: the first message after sleeping can take ~1 min. |
| Scans return few words | Set `ANTHROPIC_API_KEY` (Tesseract is only a basic fallback). |

---

## 🇺🇿 O'zbekcha: Render'ga joylash

### Tuzilma

| Xizmat | Turi | Vazifasi |
|---|---|---|
| `yodflip-web` | Web service (Docker) | Django + gunicorn **va** React ilovasi: sayt, Mini App va API bitta manzilda |
| `yodflip-bot` | Web service (Docker) | aiogram bot (**webhook** rejimi) + kunlik eslatmalar |
| `yodflip-db` | PostgreSQL | barcha ma'lumotlar, karta rasmlari ham shu yerda |

**Nega React alohida statik saytda emas, Django orqali beriladi?** Shunda sayt, API va Mini App bitta manzilda bo'ladi: CORS ham, proksi qoidalari ham kerak emas, @BotFather'ga bitta manzil beriladi.

**Nega bot "worker" emas, web service?** Webhook rejimida Telegram botga ochiq HTTPS manzil orqali murojaat qiladi, Render worker'larida esa ochiq manzil yo'q. Bot har ishga tushganda webhook'ni o'zi o'rnatadi.

### Narx va tariflar

`render.yaml` sinab ko'rish uchun **bepul** tariflardan foydalanadi. Bepul tarifning ikki kamchiligi bor:
- Web xizmatlar 15 daqiqa harakatsizlikdan so'ng "uxlab qoladi": birinchi ochilish 30–60 soniya oladi, bot eslatmalari esa bu vaqtda ishlamaydi.
- Bepul PostgreSQL **30 kundan keyin o'chadi**.

Haqiqiy foydalanuvchilar uchun web xizmatlarni `starter`, bazani `basic-256mb` tarifiga o'tkazing.

### Qadamma-qadam

1. **Bot yarating:** [@BotFather](https://t.me/BotFather) → `/newbot` → nom → username (`bot` bilan tugashi kerak). **Token**ni nusxalang.
2. Kodni **GitHub**'ga yuklang.
3. **Render → New → Blueprint** → repozitoriyani ulang. Render `render.yaml` ni o'qib, uchta resursni ko'rsatadi.
4. **Maxfiy o'zgaruvchilarni kiriting:**
   - yodflip-web: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` (`@` siz), `ANTHROPIC_API_KEY` (ixtiyoriy), `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`
   - yodflip-bot: `TELEGRAM_BOT_TOKEN` (o'sha token)

   `SECRET_KEY`, `BOT_API_SECRET`, `WEBHOOK_SECRET` va `DATABASE_URL` avtomatik yaratiladi.
5. **Apply** tugmasini bosing. Birinchi yig'ish 5–8 daqiqa oladi. `https://yodflip-web.onrender.com/api/health/` manzili `{"ok": true, "db": true}` qaytarishi kerak.
6. Agar Render boshqa manzil bergan bo'lsa, **yodflip-bot** dagi `WEBAPP_URL` ni haqiqiy manzilga o'zgartiring.
7. **@BotFather'da Mini App'ni ulang:**
   - `/setmenubutton` → botni tanlang → `https://yodflip-web.onrender.com` → tugma nomi, masalan `O'ynash`
   - `/mybots` → bot → **Bot Settings → Configure Mini App → Enable Mini App** → o'sha manzil
   - Saytdagi Telegram orqali kirish uchun: `/setdomain` → `yodflip-web.onrender.com`
8. **Sinab ko'ring:** botga `/start` yuboring va **🎮 O'yinni ochish** tugmasini bosing. Siz avtomatik tizimga kirasiz (server Telegram `initData` imzosini HTTPS orqali tekshiradi).
9. **O'z domeningiz (ixtiyoriy):** `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `PUBLIC_URL` va botdagi `WEBAPP_URL` ni yangi domenga o'zgartiring.

### Yangilash

- **Kod:** `git push` qiling. Render avtomatik qayta yig'adi, migratsiyalar o'zi bajariladi.
- **So'zlar bazasi:** `backend/words/seed/*.txt` ni o'zgartirib push qiling. Fayllar o'zgargani uchun baza bir marta qayta yuklanadi (majburan yuklash: Render Shell → `python manage.py seed_words --force`).
- **O'zgaruvchilar:** dashboard'da o'zgartiring, xizmat o'zi qayta ishga tushadi.
- **Orqaga qaytarish:** Render → xizmat → *Deploys* → avvalgi deploy → *Rollback*.
- **Admin panel:** `https://<manzil>/admin/`
