import asyncio
import re

from aiogram import Bot
from aiohttp.test_utils import TestClient, TestServer

import main
from texts import TEXTS, t


def test_webhook_secret_token_is_telegram_safe():
    tok = main.webhook_secret_token("any+base64/value==")
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", tok)
    assert tok == main.webhook_secret_token("any+base64/value==")
    assert tok != main.webhook_secret_token("other")


def test_texts_complete_in_all_languages():
    for lang in TEXTS:
        assert set(TEXTS[lang]) == set(TEXTS["uz"]), lang
    assert "19:00" in t("ru", "remind_set", time="19:00")
    assert "Yodflip" in t("uz", "welcome", name="Ali")


def update(text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Ali"},
            "text": text,
        },
    }


def test_webhook_server_checks_secret_and_serves_health():
    async def run():
        bot = Bot("123456:TEST-TOKEN-for-tests-only")
        app = main.build_webhook_app(bot, main.dp, "secret-123")
        async with TestClient(TestServer(app)) as client:
            r = await client.get("/health")
            assert r.status == 200 and (await r.json())["ok"] is True
            # wrong / missing secret header -> rejected
            r = await client.post(main.WEBHOOK_PATH, json=update("hello"))
            assert r.status == 401
            r = await client.post(
                main.WEBHOOK_PATH, json=update("hello"), headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}
            )
            assert r.status == 401
            # correct secret -> accepted (plain text has no handler, so nothing is sent to Telegram)
            r = await client.post(
                main.WEBHOOK_PATH, json=update("hello"), headers={"X-Telegram-Bot-Api-Secret-Token": "secret-123"}
            )
            assert r.status == 200

    asyncio.run(run())
