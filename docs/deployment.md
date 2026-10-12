# Betrieb und Hosting

Festgehaltene Entscheidung und **Schritt-für-Schritt-Anleitung** für den Echtbetrieb auf AWS Lightsail. Alle Befehle kannst du kopieren. Ersetze nur die Platzhalter in `GROSSBUCHSTABEN` (z. B. die Lightsail-IP).

## Entscheidung

| Punkt | Festlegung |
| --- | --- |
| Cloud | Bestehender AWS-Account der Sektion |
| Server | AWS Lightsail in der Region Frankfurt (`eu-central-1`) |
| Laufzeit | Docker Compose Produktion (`docker-compose.prod.yml`: `web` + `db` + Caddy) |
| DNS / Domain | **`auslagen.service.dav-tak.de`** (Route 53 → Lightsail-IP) |
| HTTPS | Caddy mit Let’s Encrypt |
| Backup | Täglich DB-Dump + Belege lokal, Kopie nach S3 (außerhalb des Servers) |
| Nicht | Kein EKS für dieses Tool |

Ohne funktionierendes externes Backup gilt der Betrieb nicht als fertig.

---

## Was du brauchst

- AWS-Zugang der Sektion (Lightsail + Route 53 + ein S3-Bucket für Backups)
- DNS-Rechte für `service.dav-tak.de` (A-Record `auslagen`)
- Eine E-Mail-Adresse für Let’s Encrypt (Caddy) und für ausgehende Mails (Magic Links)
- SSH-Zugang zum neuen Server

Empfohlene Lightsail-Größe zum Start: **2 GB RAM**, Ubuntu 24.04, Region **Frankfurt**. Festplatte mindestens 40 GB.

---

## 1. Lightsail-Instanz anlegen

1. In der AWS-Konsole **Lightsail** öffnen, Region **Frankfurt** wählen.
2. **Instance erstellen** → Plattform Linux/Unix → Blueprint **OS only** → **Ubuntu 24.04**.
3. Plan mit mindestens 2 GB RAM wählen.
4. Namen vergeben, z. B. `tak-auslagen`.
5. Nach dem Start unter **Networking**:
   - **Statische IP** erstellen und an die Instanz hängen.
   - Firewall: **SSH (22)**, **HTTP (80)**, **HTTPS (443)** erlauben. Port 5432 und 8000 **nicht** öffnen.
6. Die statische IP notieren: `LIGHTSAIL_IP`.

---

## 2. DNS in Route 53

1. Die Hosted Zone für `service.dav-tak.de` (bzw. die Zone, unter der dieser Name liegt) öffnen.
2. Einen **A-Record** anlegen:
   - Name: `auslagen` (vollqualifiziert: `auslagen.service.dav-tak.de`)
   - Typ: **A**
   - Wert: `LIGHTSAIL_IP`
   - TTL: 300
3. Warten, bis die Domain auflöst (oft wenige Minuten):

```bash
dig +short auslagen.service.dav-tak.de
```

Die Ausgabe muss `LIGHTSAIL_IP` sein.

---

## 3. Server vorbereiten (einmalig)

Per SSH einloggen (Lightsail-Konsole „Connect“ oder eigener SSH-Key):

```bash
ssh ubuntu@LIGHTSAIL_IP
```

Dann nacheinander:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git unzip
```

Docker installieren:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

Ausloggen und wieder einloggen, damit die Docker-Gruppe gilt:

```bash
exit
```

Erneut verbinden, dann prüfen:

```bash
docker compose version
```

AWS CLI für Backup-Upload (optional, aber empfohlen):

```bash
sudo apt-get install -y awscli
```

Projektverzeichnis:

```bash
sudo mkdir -p /opt/auslagen /var/backups/auslagen
sudo chown ubuntu:ubuntu /opt/auslagen /var/backups/auslagen
cd /opt/auslagen
git clone https://github.com/TAK-DAV/auslagen.git .
```

Wenn das Repository privat ist, nutze einen Deploy-Key oder ein Personal Access Token beim `git clone`.

---

## 4. Produktions-`.env` anlegen

```bash
cd /opt/auslagen
cp .env.example .env
nano .env
```

Trage mindestens ein (Beispielwerte ersetzen):

```bash
DJANGO_SECRET_KEY=HIER_openssl_rand_-base64_48_EINFUEGEN
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=auslagen.service.dav-tak.de
CSRF_TRUSTED_ORIGINS=https://auslagen.service.dav-tak.de
SITE_URL=https://auslagen.service.dav-tak.de
SITE_DOMAIN=auslagen.service.dav-tak.de

POSTGRES_DB=auslagen
POSTGRES_USER=auslagen
POSTGRES_PASSWORD=HIER_STARKES_PASSWORT
POSTGRES_HOST=db
POSTGRES_PORT=5432

DEFAULT_FROM_EMAIL=auslagen@dav-tak.de
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.EURE-DOMAIN.DE
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=1
```

Geheimnisse erzeugen:

```bash
openssl rand -base64 48
openssl rand -base64 24
```

`.env` darf **nicht** ins Git. Rechte absichern:

```bash
chmod 600 /opt/auslagen/.env
```

---

## 5. Anwendung starten

```bash
cd /opt/auslagen
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

Alle drei Dienste (`db`, `web`, `caddy`) sollen `running` / `healthy` sein.

Ersten Admin-Zugang anlegen:

```bash
docker compose -f docker-compose.prod.yml exec -it web python manage.py createsuperuser
```

Im Browser öffnen: `https://auslagen.service.dav-tak.de/`  
Team-Anmeldung → Authenticator → Verwaltungsbereich.

Wenn HTTPS nicht kommt: DNS noch nicht propagiert, oder Ports 80/443 in der Lightsail-Firewall fehlen.

---

## 6. Tägliches Backup (Pflicht)

### 6.1 S3-Bucket (außerhalb des Servers)

1. In AWS ein **S3-Bucket** in `eu-central-1` anlegen, z. B. `tak-auslagen-backups`.
2. Öffentlichen Zugriff blockieren.
3. Lifecycle-Regel: Objekte nach **90 Tagen** löschen oder in günstigeren Speicher überführen (Aufbewahrung Buchungsbelege länger absichern – ggf. 8+ Jahre in einem zweiten Prefix ohne Auto-Löschen).
4. IAM-User oder Instanz-Rolle mit Schreibrechten nur auf diesen Bucket. Access Key auf dem Server:

```bash
aws configure
```

### 6.2 Backup-Umgebung

```bash
sudo nano /etc/auslagen-backup.env
```

Inhalt (Passwort wie in `.env`):

```bash
PROJECT_DIR=/opt/auslagen
COMPOSE_FILE=docker-compose.prod.yml
BACKUP_DIR=/var/backups/auslagen
POSTGRES_DB=auslagen
POSTGRES_USER=auslagen
POSTGRES_PASSWORD=HIER_STARKES_PASSWORT
S3_BACKUP_URI=s3://tak-auslagen-backups/daily/
AWS_DEFAULT_REGION=eu-central-1
RETAIN_DAYS=30
```

```bash
sudo chmod 600 /etc/auslagen-backup.env
chmod +x /opt/auslagen/deploy/backup.sh
```

Einmal manuell testen:

```bash
set -a
. /etc/auslagen-backup.env
set +a
/opt/auslagen/deploy/backup.sh
aws s3 ls s3://tak-auslagen-backups/daily/
```

### 6.3 Cron täglich um 02:15 UTC

```bash
crontab -e
```

Zeile:

```cron
15 2 * * * . /etc/auslagen-backup.env; /opt/auslagen/deploy/backup.sh >> /var/log/auslagen-backup.log 2>&1
```

Log-Datei anlegen:

```bash
sudo touch /var/log/auslagen-backup.log
sudo chown ubuntu:ubuntu /var/log/auslagen-backup.log
```

---

## 7. Updates einspielen

Auf dem Server:

```bash
chmod +x /opt/auslagen/deploy/update.sh
/opt/auslagen/deploy/update.sh
```

Das Skript zieht den neuesten Stand von `main`, baut die Container neu, führt Migrationen über den Entrypoint aus und sammelt die statischen Dateien.

Vor größeren Updates: manuell ein Backup auslösen (Schritt 6.2).

---

## 8. Wiederherstellung (kurz)

Datenbank (Dump-Datei vom Backup):

```bash
cd /opt/auslagen
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U auslagen -d auslagen --clean --if-exists < /var/backups/auslagen/db/DATEI.dump
```

Belege (Media):

```bash
MEDIA_CID=$(docker compose -f docker-compose.prod.yml ps -q web)
docker run --rm --volumes-from "$MEDIA_CID" \
  -v /var/backups/auslagen/media:/backup alpine:3.20 \
  sh -c "cd /app/media && tar -xzf /backup/media-STAMP.tar.gz"
```

Danach Web neu starten:

```bash
docker compose -f docker-compose.prod.yml restart web
```

---

## 9. Absicherung gegen Spam und Angriffe

Die App drosselt Anmeldeversuche selbst:

| Stelle | Grenze (Standard) |
| --- | --- |
| Magic-Link pro IP | 5 / Stunde |
| Magic-Link pro E-Mail | 3 / Stunde |
| Team-Login (Passwort) pro IP | 10 / Stunde |
| 2FA-Code pro IP | 20 / Stunde |

Überschreitungen und fehlgeschlagene Team-Logins landen in `/var/log/auslagen/auth.log` (Zeilen mit `AUTH_RATE_LIMIT` / `AUTH_FAIL`).

### Fail2ban auf dem Server (empfohlen)

Vor dem ersten `docker compose … up` das Log-Verzeichnis anlegen:

```bash
sudo mkdir -p /var/log/auslagen
sudo chown ubuntu:ubuntu /var/log/auslagen
```

Fail2ban installieren und Filter übernehmen:

```bash
sudo apt-get install -y fail2ban
sudo cp /opt/auslagen/deploy/fail2ban/auslagen-auth.conf /etc/fail2ban/filter.d/auslagen-auth.conf
sudo cp /opt/auslagen/deploy/fail2ban/jail.auslagen.conf /etc/fail2ban/jail.d/auslagen.conf
sudo systemctl enable --now fail2ban
sudo fail2ban-client status auslagen-auth
```

Nach 8 Treffern innerhalb einer Stunde sperrt Fail2ban die IP für eine Stunde (HTTP/HTTPS). Zum Entsperren:

```bash
sudo fail2ban-client set auslagen-auth unbanip IP_ADRESSE
```

Zusätzlich gilt weiterhin: keine Selbstregistrierung, Magic Links nur an bekannte Personen, Schatzmeister mit TOTP, Postgres nicht öffentlich.

## 10. Betriebliche Checkliste

- [ ] Account und Rechnung auf die **Sektion**, nicht privat
- [ ] Statische IP + Route-53-A-Record für `auslagen.service.dav-tak.de`
- [ ] HTTPS erreichbar, Admin-Login mit 2FA
- [ ] SMTP für Magic-Link-Mails funktioniert (Test: Link anfordern)
- [ ] `/var/log/auslagen` existiert; Fail2ban-Jail `auslagen-auth` aktiv
- [ ] Einstellungen: Vereinskonto, Konten, Freistellung, Beschluss Aufwandsersatz
- [ ] Tägliches Backup läuft; Dateien liegen in **S3**
- [ ] Mindestens eine Person außer dir kennt SSH- und AWS-Zugang

---

## Bewusst nicht

- Keine Bankanbindung vom Server
- Kein EKS / Kubernetes für dieses Tool
- Keine private Hardware als Echtbetrieb

## Später möglich

ECS/Fargate plus verwaltete Datenbank, DNS weiter über Route 53. Die App ist bereits containerisiert.
