"""Bot message texts (uz default, en, ru)."""

TEXTS: dict[str, dict[str, str]] = {
    "uz": {
        "welcome": (
            "Salom, {name}! 👋\n\nYodflip — ingliz va nemis so'zlarini o'yin orqali o'rganing.\n"
            "📸 Kitob sahifasini skanerlang, 🃏 juftlash o'yinini o'ynang, 🔥 seriyangizni saqlang.\n\n"
            "Boshlash uchun tugmani bosing:"
        ),
        "open": "🎮 O'yinni ochish",
        "daily_title": "📅 Bugungi kunlik musobaqa — hamma uchun bir xil 10 ta so'z:",
        "play_daily": "📅 Kunlik musobaqani o'ynash",
        "stats": (
            "📊 Sizning natijangiz\n\n⭐ Daraja: {level} ({xp} XP)\n🔥 Seriya: {streak} kun\n"
            "EN · Ingliz: {en_learned} o'rganildi / {en_total} ko'rildi\n"
            "DE · Nemis: {de_learned} o'rganildi / {de_total} ko'rildi\nBugun: {today}"
        ),
        "review": "🔁 Takrorlash vaqti keldi:\nEN · Ingliz: {en} ta so'z\nDE · Nemis: {de} ta so'z",
        "review_none": "🎉 Hozircha takrorlash uchun so'z yo'q. Yangi so'zlar o'rganing!",
        "play_review": "🔁 Takrorlashni boshlash",
        "not_registered": "Avval ilovani bir marta oching — hisobingiz avtomatik yaratiladi.",
        "remind_help": "⏰ Kunlik eslatma: /remind 19:00  (o'chirish: /remind off)",
        "remind_set": "⏰ Tayyor! Har kuni {time} da, agar o'sha kuni o'ynamagan bo'lsangiz, eslataman.",
        "remind_off": "🔕 Eslatmalar o'chirildi.",
        "reminder": "🔥 Bugun hali mashq qilmadingiz! Seriya: {streak} kun. Takrorlashga {due} ta so'z kutmoqda.",
        "error": "Xatolik yuz berdi. Birozdan so'ng urinib ko'ring.",
    },
    "en": {
        "welcome": (
            "Hi, {name}! 👋\n\nYodflip — learn English and German words by playing.\n"
            "📸 Scan a book page, 🃏 play the match game, 🔥 keep your streak.\n\nTap the button to start:"
        ),
        "open": "🎮 Open game",
        "daily_title": "📅 Today's Daily Challenge — the same 10 words for everyone:",
        "play_daily": "📅 Play the Daily Challenge",
        "stats": (
            "📊 Your progress\n\n⭐ Level: {level} ({xp} XP)\n🔥 Streak: {streak} days\n"
            "EN · English: {en_learned} learned / {en_total} seen\n"
            "DE · German: {de_learned} learned / {de_total} seen\nToday: {today}"
        ),
        "review": "🔁 Words due for review:\nEN · English: {en}\nDE · German: {de}",
        "review_none": "🎉 Nothing to review right now. Learn some new words!",
        "play_review": "🔁 Start review",
        "not_registered": "Open the app once first — your account is created automatically.",
        "remind_help": "⏰ Daily reminder: /remind 19:00  (turn off: /remind off)",
        "remind_set": "⏰ Done! I'll remind you at {time} every day if you haven't played yet.",
        "remind_off": "🔕 Reminders turned off.",
        "reminder": "🔥 You haven't practised today! Streak: {streak} days. {due} words are due for review.",
        "error": "Something went wrong. Please try again later.",
    },
    "ru": {
        "welcome": (
            "Привет, {name}! 👋\n\nYodflip — учите английские и немецкие слова, играя.\n"
            "📸 Сканируйте страницу учебника, 🃏 играйте в «Пары», 🔥 держите серию.\n\nНажмите кнопку, чтобы начать:"
        ),
        "open": "🎮 Открыть игру",
        "daily_title": "📅 Ежедневный вызов — 10 одинаковых слов для всех:",
        "play_daily": "📅 Играть ежедневный вызов",
        "stats": (
            "📊 Ваш прогресс\n\n⭐ Уровень: {level} ({xp} XP)\n🔥 Серия: {streak} дн.\n"
            "EN · Английский: выучено {en_learned} / встречено {en_total}\n"
            "DE · Немецкий: выучено {de_learned} / встречено {de_total}\nСегодня: {today}"
        ),
        "review": "🔁 Пора повторить:\nEN · Английский: {en}\nDE · Немецкий: {de}",
        "review_none": "🎉 Сейчас повторять нечего. Выучите новые слова!",
        "play_review": "🔁 Начать повторение",
        "not_registered": "Сначала откройте приложение — аккаунт создастся автоматически.",
        "remind_help": "⏰ Напоминание: /remind 19:00  (выключить: /remind off)",
        "remind_set": "⏰ Готово! Напомню в {time}, если вы ещё не занимались в этот день.",
        "remind_off": "🔕 Напоминания выключены.",
        "reminder": "🔥 Сегодня вы ещё не занимались! Серия: {streak} дн. Ждут повторения: {due} слов.",
        "error": "Произошла ошибка. Попробуйте позже.",
    },
}


def t(lang: str, key: str, **kw) -> str:
    table = TEXTS.get(lang) or TEXTS["uz"]
    return table.get(key, TEXTS["uz"][key]).format(**kw)
