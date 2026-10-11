import hashlib
import os

from django.core.exceptions import ValidationError

ALLOWED_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def validate_receipt_file(uploaded) -> None:
    extension = os.path.splitext(uploaded.name)[1].lower()
    if extension not in ALLOWED_RECEIPT_EXTENSIONS:
        raise ValidationError("Erlaubt sind Foto (JPEG, PNG, WEBP, HEIC) oder PDF.")


def sha256_of_file(uploaded) -> str:
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    return digest.hexdigest()


def receipt_upload_to(instance, filename: str) -> str:
    return f"receipts/{instance.report_id}/{filename}"
