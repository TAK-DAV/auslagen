"""Simple IP/identity rate limits using Django's cache (shared via DB cache in prod)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("auslagen.auth")


def client_ip(request) -> str:
    """Client address. Behind Caddy we trust the first X-Forwarded-For hop."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.META.get("REMOTE_ADDR") or "unknown"


def is_limited(bucket: str, identity: str, *, limit: int, window_seconds: int) -> bool:
    """Return True when the identity has already used `limit` hits in the window."""
    if limit <= 0:
        return False
    key = f"rl:{bucket}:{identity}"
    try:
        count = cache.get(key)
        if count is None:
            cache.add(key, 1, timeout=window_seconds)
            return False
        if int(count) >= limit:
            return True
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, int(count) + 1, timeout=window_seconds)
        return False
    except Exception:  # noqa: BLE001 - never break login if cache is down
        logger.exception("Rate-limit cache error for %s", key)
        return False


def hit(bucket: str, identity: str, *, limit: int, window_seconds: int) -> bool:
    """Record a hit and return True if the limit is now exceeded (or was already)."""
    return is_limited(bucket, identity, limit=limit, window_seconds=window_seconds)


def magic_link_limits() -> tuple[int, int]:
    return (
        int(getattr(settings, "RATELIMIT_MAGIC_LINK_IP", 5)),
        int(getattr(settings, "RATELIMIT_MAGIC_LINK_WINDOW", 3600)),
    )


def staff_login_limits() -> tuple[int, int]:
    return (
        int(getattr(settings, "RATELIMIT_STAFF_LOGIN_IP", 10)),
        int(getattr(settings, "RATELIMIT_STAFF_LOGIN_WINDOW", 3600)),
    )


def log_rate_limited(request, *, action: str) -> None:
    ip = client_ip(request)
    logger.warning("AUTH_RATE_LIMIT action=%s ip=%s path=%s", action, ip, request.path)


def log_auth_failed(request, *, action: str, detail: str = "") -> None:
    ip = client_ip(request)
    logger.warning(
        "AUTH_FAIL action=%s ip=%s path=%s detail=%s",
        action,
        ip,
        request.path,
        detail,
    )
