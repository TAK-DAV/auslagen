from datetime import date


def club_year_start(value: date) -> int:
    """Calendar year of 1 May, when the club year (1 May–30 April) begins."""
    if value.month >= 5:
        return value.year
    return value.year - 1


def club_year_label(start_year: int | None) -> str:
    if not start_year:
        return "—"
    return f"{start_year}/{start_year + 1}"
