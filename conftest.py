import os
from pathlib import Path

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-for-production")
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("POSTGRES_DB", "auslagen")
os.environ.setdefault("POSTGRES_USER", "auslagen")
os.environ.setdefault("POSTGRES_PASSWORD", "auslagen")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("SITE_URL", "http://testserver")
# Avoid writing auth logs under /var/log during pytest import of settings.
os.environ.setdefault("AUTH_LOG_FILE", str(Path("/tmp") / "auslagen-test-auth.log"))

import pytest


@pytest.fixture(autouse=True)
def isolated_media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def locmem_cache(settings):
    """Use in-memory cache so rate-limit tests stay isolated and need no DB table."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "auslagen-test",
        }
    }
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def seeded(db):
    from masterdata.seed import seed_masterdata

    seed_masterdata()
