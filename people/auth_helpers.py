from people.roles import ADMIN, APPROVER, TREASURER


def user_requires_staff_login(user) -> bool:
    """Freigeber, Schatzmeister and admins use password plus TOTP, not magic links."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=[APPROVER, TREASURER, ADMIN]).exists()


def user_can_submit_expenses(user) -> bool:
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user_requires_staff_login(user):
        return False
    return True
