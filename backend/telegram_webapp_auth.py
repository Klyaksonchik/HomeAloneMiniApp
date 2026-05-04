"""Проверка целостности Telegram WebApp initData (Mini App)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
) -> dict[str, Any] | None:
    """
    Проверяет подпись initData и свежесть auth_date.
    Возвращает словарь полей (без hash/signature) или None.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not bot_token:
        return None
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    except ValueError:
        return None
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    data.pop("signature", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    dcs = data_check_string.encode("utf-8")
    # В документации формулировка двусмысленна: пробуем оба порядка key/msg для первого HMAC.
    secret_keys = (
        hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest(),
        hmac.new(bot_token.encode("utf-8"), b"WebAppData", hashlib.sha256).digest(),
    )
    if not any(
        hmac.compare_digest(
            hmac.new(sk, dcs, hashlib.sha256).hexdigest(),
            received_hash,
        )
        for sk in secret_keys
    ):
        logger.debug("initData: подпись не сошлась ни с одним вариантом secret_key")
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
