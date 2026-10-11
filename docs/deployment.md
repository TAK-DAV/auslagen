# Betrieb und Hosting

Festgehaltene Entscheidung für den Echtbetrieb. Die Schritt-für-Schritt-Anleitung kommt in Phase 7, wenn die App steht.

## Entscheidung

| Punkt | Festlegung |
| --- | --- |
| Cloud | Bestehender AWS-Account der Sektion |
| Server | AWS Lightsail in der Region Frankfurt (`eu-central-1`) |
| Laufzeit | Docker Compose, dieselbe Struktur wie lokal (`web` + `db`) |
| DNS | Route 53; eine der beiden vorhandenen Subdomains zeigt auf den Lightsail-Server |
| HTTPS | Reverse Proxy auf dem Server (Caddy oder Nginx) mit gültigem Zertifikat |
| Nicht | Kein EKS für dieses Tool. ECS/Fargate bleibt eine spätere Option, kein Startpfad |

EKS bleibt für das, was dort schon läuft. Dieses Tool ist eine kleine Django-App mit PostgreSQL und Belegdateien; ein fester Lightsail-Server reicht dafür und ist einfacher zu übergeben, wenn das Schatzmeisteramt wechselt.

## Was auf dem Server liegt

- Django-Anwendung und PostgreSQL in Docker Compose
- Belege als Datei-Volume auf dem Server
- Reverse Proxy vor Port 443
- Umgebungsvariablen aus einer lokalen `.env` auf dem Server (nie im Repository)

## Backup

Täglich, automatisch, **außerhalb** des Lightsail-Servers:

- PostgreSQL-Dump
- Beleg-Volume (Originaldateien)

Ziel und Aufbewahrungsdauer legt Phase 7 fest. Ohne externes Backup gilt der Betrieb nicht als fertig.

## DNS (Route 53)

Zwei Subdomains liegen schon in Route 53. Eine davon bekommt einen Eintrag auf die öffentliche IP (oder die statische IP) der Lightsail-Instanz. Zertifikat und App laufen unter dieser Subdomain.

# FACHLICH OFFEN: welche der beiden Subdomains für das Auslagen-Tool gilt.

## Bewusst nicht jetzt

- Keine Bankanbindung vom Server aus
- Kein Kubernetes, kein zweites Cluster nur für Auslagen
- Keine private Hardware und kein privater AWS-Account als Echtbetrieb

## Später möglich

Wenn der Verein später alles auf verwaltete AWS-Dienste legen will: ECS/Fargate plus verwaltete Datenbank, DNS weiter über Route 53. Der Wechsel ist möglich, weil die App schon als Container gebaut ist. Das ist kein Grund, den Start zu verzögern.
