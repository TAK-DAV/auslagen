import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.urls import reverse

from people.models import Person
from people.roles import TREASURER
from portal.ratelimit import client_ip, hit, is_limited


@pytest.mark.django_db
def test_is_limited_allows_up_to_limit_then_blocks():
    assert is_limited("t", "a", limit=3, window_seconds=60) is False
    assert is_limited("t", "a", limit=3, window_seconds=60) is False
    assert is_limited("t", "a", limit=3, window_seconds=60) is False
    assert is_limited("t", "a", limit=3, window_seconds=60) is True
    assert hit("t", "a", limit=3, window_seconds=60) is True


@pytest.mark.django_db
def test_limit_zero_disables_bucket():
    assert is_limited("off", "x", limit=0, window_seconds=60) is False
    assert is_limited("off", "x", limit=0, window_seconds=60) is False


def test_client_ip_prefers_forwarded_for(rf):
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.1")
    assert client_ip(request) == "203.0.113.9"
    request = rf.get("/", REMOTE_ADDR="127.0.0.1")
    assert client_ip(request) == "127.0.0.1"


@pytest.fixture
def submitter(db):
    from django.utils import timezone

    from people.roles import SUBMITTER

    person = Person.objects.create_user(
        "einreicher@example.org",
        password="unused",
        first_name="Eva",
        last_name="Berg",
    )
    person.privacy_acknowledged_at = timezone.now()
    person.save()
    Group.objects.get_or_create(name=SUBMITTER)
    person.groups.add(Group.objects.get(name=SUBMITTER))
    return person


@pytest.mark.django_db
def test_magic_link_ip_rate_limit(client, submitter, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_MAGIC_LINK_IP = 2
    settings.RATELIMIT_MAGIC_LINK_EMAIL = 100
    settings.RATELIMIT_MAGIC_LINK_WINDOW = 3600
    url = reverse("portal:login_request")
    assert client.post(url, {"email": submitter.email}).status_code == 200
    assert client.post(url, {"email": submitter.email}).status_code == 200
    assert len(mail.outbox) == 2
    response = client.post(url, {"email": submitter.email})
    assert response.status_code == 200
    assert b"Zu viele Anfragen" in response.content
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_magic_link_email_rate_limit(client, submitter, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.RATELIMIT_MAGIC_LINK_IP = 100
    settings.RATELIMIT_MAGIC_LINK_EMAIL = 1
    settings.RATELIMIT_MAGIC_LINK_WINDOW = 3600
    url = reverse("portal:login_request")
    assert client.post(url, {"email": submitter.email}).status_code == 200
    assert len(mail.outbox) == 1
    response = client.post(url, {"email": submitter.email})
    assert b"Zu viele Anfragen" in response.content
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_staff_login_rate_limit(client, settings):
    settings.RATELIMIT_STAFF_LOGIN_IP = 2
    settings.RATELIMIT_STAFF_LOGIN_WINDOW = 3600
    Group.objects.get_or_create(name=TREASURER)
    Person.objects.create_user(
        "kasse@example.org",
        password="secret-pass",
        first_name="Kai",
        last_name="Kasse",
        is_staff=True,
    )
    treasurer = Person.objects.get(email="kasse@example.org")
    treasurer.groups.add(Group.objects.get(name=TREASURER))
    url = reverse("portal:staff_login")
    for _ in range(2):
        response = client.post(
            url,
            {"email": "kasse@example.org", "password": "wrong"},
        )
        assert response.status_code == 200
        assert b"Anmeldung fehlgeschlagen" in response.content
    response = client.post(
        url,
        {"email": "kasse@example.org", "password": "wrong"},
    )
    assert b"Zu viele Anmeldeversuche" in response.content
