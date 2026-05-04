"""Проверка целостности Telegram WebApp initData (Mini App)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def _parse_init_data_pairs(init_data: str) -> dict[str, str]:
    """
    Разбор строки initData как query string.
    Важно: не использовать parse_qsl — он применяет unquote_plus и '+' становится пробелом,
    из‑за чего подпись не совпадает с тем, что считает Telegram.
    См. https://stackoverflow.com/a/72391757
    """
    init_data = (init_data or "").strip()
    if init_data.startswith("?"):
        init_data = init_data[1:]
    out: dict[str, str] = {}
    for part in init_data.split("&"):
        if not part or "=" not in part:
            continue
        key, _, val = part.partition("=")
        k = unquote(key)
        v = unquote(val)
        out[k] = v
    return out


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
) -> dict[str, Any] | None:
    """
    Проверяет подпись initData и свежесть auth_date.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not bot_token:
        return None
    try:
        data = _parse_init_data_pairs(init_data)
    except Exception:
        return None
    received_hash = data.pop("hash", None)
    data.pop("signature", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    dcs = data_check_string.encode("utf-8")
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    computed = hmac.new(secret_key, dcs, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        logger.warning("initData: подпись не сошлась (проверьте BOT_TOKEN и целостность строки)")
        return None
    auth_date_raw = data.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except (TypeError, ValueError):
            return None
        if int(time.time()) - auth_date > max_age_seconds:
            logger.warning("initData: устаревший auth_date")
            return None
    return data


def telegram_user_id_from_init_data(init_data: str, bot_token: str) -> int | None:
    """Из проверенного initData возвращает user.id или None."""
    fields = validate_telegram_init_data(init_data, bot_token)
    if not fields:
        return None
    raw_user = fields.get("user")
    if not raw_user:
        return None
    try:
        user = json.loads(raw_user)
    except (json.JSONDecodeError, TypeError):
        return None
    uid = user.get("id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None
