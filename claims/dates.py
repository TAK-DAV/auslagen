import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

BERLIN = ZoneInfo("Europe/Berlin")


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def waiver_is_late(expense_date: date, waiver_on: date) -> bool:
    """True when the waiver is more than three calendar months after the expense."""
    return waiver_on > add_months(expense_date, 3)


def local_date(value: datetime) -> date:
    if timezone.is_aware(value):
        return value.astimezone(BERLIN).date()
    return value.date()
