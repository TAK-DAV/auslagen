import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from people.models import LoginToken


def _hash(raw: str) -> str:
    pepper = settings.SECRET_KEY
    return hashlib.sha256(f"{pepper}:{raw}".encode()).hexdigest()


def create_login_token(user, *, minutes_valid: int = 30) -> str:
    raw = secrets.token_urlsafe(32)
    LoginToken.objects.create(
        user=user,
        token_hash=_hash(raw),
        expires_at=timezone.now() + timedelta(minutes=minutes_valid),
    )
    return raw


def consume_login_token(raw: str):
    token_hash = _hash(raw)
    token = (
        LoginToken.objects.select_related("user")
        .filter(token_hash=token_hash, used_at__isnull=True, expires_at__gt=timezone.now())
        .first()
    )
    if token is None:
        return None
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])
    return token.user


def send_magic_link_email(user, raw_token: str) -> None:
    site = settings.SITE_URL.rstrip("/")
    path = settings.LOGIN_TOKEN_PATH.format(token=raw_token)
    login_url = f"{site}{path}"
    subject = "Anmeldelink – TAK Auslagen"
    body = render_to_string(
        "email/magic_link.txt",
        {"user": user, "login_url": login_url, "minutes": 30},
    )
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
