from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from people.iban import normalize_iban, validate_iban


class MemberType(models.TextChoices):
    VOLUNTEER = "EHRENAMT", "Ehrenamt"
    EMPLOYEE = "ANGESTELLT", "Angestellt"


class PersonManager(UserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class Person(AbstractUser):
    """A club member who submits expenses or reviews them.

    Login arrives later: a magic link for submitters, password plus TOTP
    for approvers, the treasurer and admins.
    """

    username = None
    email = models.EmailField("E-Mail", unique=True)
    member_type = models.CharField(
        "Art",
        max_length=20,
        choices=MemberType.choices,
        default=MemberType.VOLUNTEER,
    )
    iban = models.CharField(
        "IBAN",
        max_length=42,
        blank=True,
        validators=[validate_iban],
        help_text="Wird für die Überweisung gebraucht. Leerzeichen sind erlaubt.",
    )
    street = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    postal_code = models.CharField("Postleitzahl", max_length=20, blank=True)
    city = models.CharField("Ort", max_length=100, blank=True)
    address_country = models.CharField(
        "Land der Anschrift",
        max_length=2,
        blank=True,
        help_text="ISO-Kürzel, zum Beispiel DE oder AT. Pflicht nur bei einem Verzicht.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = PersonManager()

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["last_name", "first_name", "email"]

    def clean(self):
        super().clean()
        self.email = type(self).objects.normalize_email(self.email).lower()
        self._normalize_iban()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = type(self).objects.normalize_email(self.email).lower()
        self._normalize_iban()
        super().save(*args, **kwargs)

    def _normalize_iban(self):
        if not self.iban:
            return
        self.iban = normalize_iban(self.iban)
        validate_iban(self.iban)

    def __str__(self):
        full_name = self.get_full_name().strip()
        return full_name or self.email

    @property
    def has_postal_address(self) -> bool:
        return bool(self.street and self.postal_code and self.city and self.address_country)
