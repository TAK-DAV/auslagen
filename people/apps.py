from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "people"
    verbose_name = "Personen"

    def ready(self):
        from django.contrib import admin

        admin.site.site_header = "TAK Auslagen"
        admin.site.site_title = "TAK Auslagen"
        admin.site.index_title = "Stammdaten und Abrechnungen"
