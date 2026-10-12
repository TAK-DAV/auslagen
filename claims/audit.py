"""Write AuditLog rows for changes after a report is no longer a draft."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

from claims.models import AuditLog


def log_change(
    *,
    actor,
    obj,
    field_name: str,
    old_value,
    new_value,
    reason: str = "",
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        content_type=ContentType.objects.get_for_model(obj.__class__),
        object_id=obj.pk,
        field_name=field_name,
        old_value="" if old_value is None else str(old_value),
        new_value="" if new_value is None else str(new_value),
        reason=reason or "",
    )


def log_many(*, actor, obj, changes: dict, reason: str = "") -> list[AuditLog]:
    """changes: field_name -> (old, new)"""
    entries = []
    for field_name, (old_value, new_value) in changes.items():
        if old_value == new_value:
            continue
        entries.append(
            log_change(
                actor=actor,
                obj=obj,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
            )
        )
    return entries
