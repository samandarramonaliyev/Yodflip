"""Telegram authentication helpers.

* Mini App: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
  secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
* Login Widget: https://core.telegram.org/widgets/login#checking-authorization
  secret_key = SHA256(bot_token)
  hash       = HMAC_SHA256(key=secret_key, msg=data_check_string)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode


class TelegramAuthError(Exception):
    pass


def _data_check_string(pairs: dict[str, str]) -> str:
    return "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))


def verify_init_data(init_data: str, bot_token: str, max_age: int | None = 86400, now: float | None = None) -> dict:
    """Validate Mini App initData and return the parsed payload (with `user` decoded)."""
    if not init_data or not bot_token:
        raise TelegramAuthError("missing_init_data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("missing_hash")
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, _data_check_string(pairs).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise TelegramAuthError("bad_hash")
    _check_age(pairs.get("auth_date"), max_age, now)
    result: dict = dict(pairs)
    if "user" in pairs:
        try:
            result["user"] = json.loads(pairs["user"])
        except json.JSONDecodeError as exc:
            raise TelegramAuthError("bad_user_json") from exc
    return result


def verify_login_widget(data: dict, bot_token: str, max_age: int | None = 86400, now: float | None = None) -> dict:
    """Validate a Telegram Login Widget payload (id, first_name, ..., auth_date, hash)."""
    if not bot_token:
        raise TelegramAuthError("missing_token")
    fields = {k: str(v) for k, v in data.items() if v is not None and k != "hash"}
    received_hash = str(data.get("hash", ""))
    if not received_hash:
        raise TelegramAuthError("missing_hash")
    secret = hashlib.sha256(bot_token.encode()).digest()
    calc = hmac.new(secret, _data_check_string(fields).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise TelegramAuthError("bad_hash")
    _check_age(fields.get("auth_date"), max_age, now)
    return {
        "user": {
            "id": int(fields["id"]),
            "first_name": fields.get("first_name", ""),
            "last_name": fields.get("last_name", ""),
            "username": fields.get("username", ""),
            "photo_url": fields.get("photo_url", ""),
        }
    }


def parse_unsigned_init_data(init_data: str) -> dict:
    """MOCK mode only: parse initData without signature checks."""
    pairs = dict(parse_qsl(init_data or "", keep_blank_values=True))
    if "user" in pairs:
        user = json.loads(pairs["user"])
    else:
        user = {"id": 1000001, "first_name": "Demo", "username": "demo_user"}
    return {"user": user}


def _check_age(auth_date: str | None, max_age: int | None, now: float | None) -> None:
    if max_age is None:
        return
    try:
        ts = int(auth_date or "0")
    except ValueError as exc:
        raise TelegramAuthError("bad_auth_date") from exc
    if (now or time.time()) - ts > max_age:
        raise TelegramAuthError("expired")


def sign_init_data(pairs: dict[str, str], bot_token: str) -> str:
    """Build a correctly signed initData string (used by tests and local tooling)."""
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, _data_check_string(pairs).encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": h})


def sign_login_widget(fields: dict, bot_token: str) -> dict:
    secret = hashlib.sha256(bot_token.encode()).digest()
    str_fields = {k: str(v) for k, v in fields.items()}
    h = hmac.new(secret, _data_check_string(str_fields).encode(), hashlib.sha256).hexdigest()
    return {**fields, "hash": h}
