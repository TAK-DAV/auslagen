# TAK Auslagen

Web-App für die Auslagen einer DAV-Sektion. Ehrenamtliche und Angestellte reichen Belege ein, zwei Personen prüfen, am Ende stehen Buchungsliste, SEPA-Datei und bei Verzicht eine Zuwendungsbestätigung.

Stammdaten, Steuerlogik, Einreichportal und **Freigabe-Workflow** stehen. Freigeber prüfen Positionen je Kostenstelle, der Schatzmeister gibt final frei; Rückfragen gehen per Mail zurück an den Einreicher. Spenden-PDF und Exporte folgen als Nächstes.

## Was du zum Start brauchst

Docker und das Compose-Plugin. Prüfung:

```bash
docker compose version
```

Die Ausgabe nennt eine Versionsnummer. Wenn der Befehl fehlt, installiere Docker Engine und das Plugin `docker-compose-v2`, auf dem eigenen Rechner alternativ Docker Desktop.

## Start

Die Befehle gelten im Projektordner, also dort, wo `docker-compose.yml` liegt.

1. Lege die lokale Konfiguration an:

```bash
cp .env.example .env
```

2. Erzeuge einen geheimen Schlüssel:

```bash
openssl rand -base64 48
```

3. Öffne die Datei `.env` in einem Editor. Ersetze `change-me` bei `DJANGO_SECRET_KEY` durch den eben erzeugten Schlüssel. Ersetze `change-me` bei `POSTGRES_PASSWORD` durch ein selbst gewähltes Passwort. Speichere die Datei. `.env` bleibt auf diesem Rechner und wird nicht ins Repository übernommen.

4. Starte Datenbank und Anwendung:

```bash
docker compose up --build
```

Der erste Start lädt das PostgreSQL-Image und baut die Anwendung. Das Fenster bleibt offen. Wenn dort `Starting development server at http://0.0.0.0:8000/` steht, läuft die App. Migrationen und Beispiel-Stammdaten sind dabei schon gelaufen.

5. Öffne ein zweites Terminal im selben Ordner und lege den ersten Zugang an:

```bash
docker compose exec -it web python manage.py createsuperuser
```

Die Abfrage erwartet eine E-Mail-Adresse und zweimal ein Passwort. Das ist der technische Zugang für den Verwaltungsbereich, noch nicht die spätere Anmeldung für Einreicher.

6. Öffne [http://localhost:8000/](http://localhost:8000/). **Auslagen einreichen** für Ehrenamtliche (Magic Link erscheint in der Docker-Konsole, solange `EMAIL_BACKEND` auf Konsole steht). **Team-Anmeldung** für Freigeber und Schatzmeister: Passwort, Authenticator einrichten, dann Verwaltungsbereich.

### Einreicher durchspielen

1. Im Verwaltungsbereich eine Person anlegen (aktiv, ohne Freigeber-/Schatzmeister-Rolle). IBAN eintragen.
2. `/einreichen/anmelden/` → E-Mail → Link aus der Konsole öffnen → Datenschutz bestätigen.
3. Abrechnung anlegen, Position mit Beleg (Handy: Kamera) speichern, unter **Einreichen** abschließen.

7. Beenden im ersten Terminal mit Strg+C. Beim nächsten Mal genügt:

```bash
docker compose up
```

Wenn der Start meldet, dass Port 5432 oder 8000 schon belegt ist, beendet das andere Programm oder ändert in `docker-compose.yml` die linke Seite von `"5432:5432"` beziehungsweise `"8000:8000"`.

## Was im Verwaltungsbereich liegt

- **Kostenstellen.** Elf Beispielstellen, darunter Rotwandhaus, Babenstuber Hütte und Gruttenhütte, jeweils Betrieb und Wanderwege. Ein Hinweis in der Spalte „Hinweis zur fachlichen Klärung“ markiert Stellen, deren Sphäre noch offen ist.
- **Steuersätze.** Deutschland 19 %, 7 %, 0 %. Österreich 20 %, 13 %, 10 %, 0 %. Das Datum „Gültig ab“ ist ein Platzhalter.
- **Kilometer-Satz.** Ein Standard von 0,30 €. Der Satz 0 ist erlaubt. Sätze je Rolle und Anlass fehlen noch.
- **Einstellungen.** Kleinbetragsgrenzen 250 € (DE) und 400 € (AT). Die Spendenoption bleibt aus, bis Datum und Fundstelle des Beschlusses zum Aufwandsersatz eingetragen sind. Verzicht für Angestellte ist zusätzlich ausgeschaltet.
- **Sachkonten.** Bewusst leer. Der Kontenrahmen kommt aus der bestehenden Buchhaltung und wird hier eingetragen, nicht erfunden.
- **Personen, Abrechnungen, Positionen, Belege, Zahlungsläufe, Zuwendungsbestätigungen, Änderungsprotokoll.**

### Freigabe (Team)

1. Person als Freigeber anlegen, Gruppe **Freigeber**, der Kostenstelle unter **Freigeber** zuordnen.
2. Schatzmeister: Gruppe **Schatzmeister**, Team-Anmeldung + Authenticator.
3. Nach Einreichung: `/einreichen/pruefung/` → Position freigeben oder Rückfrage.
4. Wenn alle Positionen ok: `/einreichen/schatzmeister/` → final freigeben (Vollverzicht → Status Erledigt).

Wanderwege lassen sich nicht auf einen Vorsteuerabzug umstellen und nicht aus dem ideellen Bereich herausnehmen. Eine Person kann die eigenen Positionen nicht sachlich freigeben. Nach einer Auszahlung lässt sich der Verzicht nicht mehr ändern. Statusänderungen und Freigaben stehen im **Änderungsprotokoll**.

## Tests

Im zweiten Terminal, während die Anwendung läuft:

```bash
docker compose exec web pytest
```

Am Ende steht eine Zeile mit der Anzahl bestandener Tests. Eine fehlgeschlagene Prüfung ist rot markiert.

## Festgelegte Regeln

- Die sachliche Freigabe gilt je Position. Eine Abrechnung geht erst weiter, wenn jede Position von einem Freigeber ihrer Kostenstelle geprüft ist.
- Verzicht und Auszahlung sind zwei Beträge. Der Status folgt nur dem Betrag, der überwiesen wird.
- Steuer = Brutto − Brutto / (1 + Satz), je Position kaufmännisch auf den Cent. Netto = Brutto − Steuer. Niemals Gleitkomma.
- Vorsteuer: keine bei Kostenstelle ohne Abzug; DE bzw. AT nur wenn Modus und Belegland passen; sonst und bei „Sonstiges“ → Prüfung nötig. DE- und AT-Summen bleiben getrennt.
- Über der Kleinbetragsgrenze (DE 250 €, AT 400 €) erscheint ein Hinweis auf eine vollständige Rechnung.
- Vorschüsse sind nicht enthalten.

## Betrieb

Echtbetrieb: AWS Lightsail in Frankfurt, Docker Compose wie lokal, DNS über die vorhandenen Route-53-Subdomains, HTTPS auf dem Server, tägliches Backup von Datenbank und Belegen außerhalb des Servers. Kein EKS für dieses Tool. Details und offene Punkte: [docs/deployment.md](docs/deployment.md). Die genaue Server-Anleitung folgt in Phase 7.

## Fachlich offen

Diese Punkte sind im Verwaltungsbereich oder im Code mit `FACHLICH OFFEN` markiert. Ein erneutes Anlegen der Stammdaten überschreibt spätere Änderungen nicht.

- Sphäre von Ausbildung, Touren, den drei Hüttenbetrieben und dem Rotwandhaus-Fahrweg.
- Wer je Kostenstelle sachlich freigibt, und wer vertritt.
- Welcher Kilometer-Satz für welche Rolle und welchen Anlass gilt.
- Der echte Kontenrahmen und das Mapping Kostenstelle × Auslagenart.
- Der vollständige Vereinsname und die Daten des Freistellungsbescheids.
- Ob und wann ein Vorstandsbeschluss zum Aufwandsersatz vorliegt.
- Ob Angestellte auf Reisekosten verzichten dürfen.
- Das Gültig-ab der hinterlegten Steuersätze.
- Die echten Namen der OneDrive-Themenordner.
- Der Nummernkreis der Belegnummer.
- Bei mehreren Positionen zählt für die Drei-Monats-Warnung beim Verzicht das älteste Auslagedatum.

Belege, bei denen das Land des Belegs nicht zum Land der Kostenstelle passt, bleiben zur manuellen Entscheidung und stehen als „Prüfung nötig“. Eine andere Vorsteuer braucht dann eine Begründung.
