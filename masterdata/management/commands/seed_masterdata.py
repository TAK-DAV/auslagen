from django.core.management.base import BaseCommand

from masterdata.seed import seed_masterdata


class Command(BaseCommand):
    help = (
        "Legt Sphären, Steuersätze, Hütten, Kostenstellen, den Kilometer-Satz "
        "und die Grundeinstellungen an. Vorhandene Einträge bleiben unverändert."
    )

    def handle(self, *args, **options):
        seed_masterdata()
        self.stdout.write(self.style.SUCCESS("Stammdaten sind angelegt."))
