from django.db import models


class Country(models.TextChoices):
    DE = "DE", "Deutschland"
    AT = "AT", "Österreich"


class VatMode(models.TextChoices):
    NONE = "KEINE", "Keine Vorsteuer"
    DE = "DE", "Vorsteuer Deutschland"
    AT = "AT", "Vorsteuer Österreich"


class Area(models.TextChoices):
    OPERATION = "BETRIEB", "Betrieb / Gebäude"
    ACCESS_ROAD = "FAHRWEG", "Fahrweg"
    TRAILS = "WANDERWEGE", "Wanderwege"


class ExpenseType(models.TextChoices):
    CAR = "FAHRT_PKW", "Fahrtkosten Pkw"
    TRANSIT = "FAHRT_OEPNV", "Fahrtkosten ÖPNV, Bahn, Maut, Parken"
    HOSPITALITY = "BEWIRTUNG_EXTERN", "Bewirtung Externer"
    CREW_MEALS = "VERPFLEGUNG_HELFER", "Verpflegung interner Helfer"
    HUT_MATERIAL = "MATERIAL_HUETTE", "Material / Leistungen Hütte"
    LODGING = "UEBERNACHTUNG", "Übernachtung"
    OTHER = "SONSTIGES", "Sonstiges"


class VatResult(models.TextChoices):
    NONE = "KEINE", "Keine Vorsteuer"
    DE = "DE", "Vorsteuer Deutschland"
    AT = "AT", "Vorsteuer Österreich"
    REVIEW = "PRUEFEN", "Prüfung nötig"


class SphereCode:
    NON_PROFIT = "IDEELL"
    ASSET_MANAGEMENT = "VERMOEGENSVERWALTUNG"
    PURPOSE_BUSINESS = "ZWECKBETRIEB"
    COMMERCIAL = "WIRTSCHAFTLICH"
