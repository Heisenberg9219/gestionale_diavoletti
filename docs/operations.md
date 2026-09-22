# Operazioni di produzione

## Backup PostgreSQL

Lo script `infrastructure/scripts/backup_postgres.py` crea un dump PostgreSQL in formato custom e conserva gli ultimi sette file. I dump sono archiviati in `infrastructure/backups/`, esclusa da Git.

Sul server, eseguire il processo con l'utente `deploy`, autorizzato a usare Docker. Dopo il primo deploy creare la directory dei log e aggiungere al crontab:

```cron
0 2 * * * cd /srv/diavoletti && COMPOSE_FILE=/srv/diavoletti/infrastructure/compose.server.yml COMPOSE_ENV_FILE=/srv/diavoletti/.env BACKUP_DIR=/srv/diavoletti/infrastructure/backups /usr/bin/python3 infrastructure/scripts/backup_postgres.py >> /srv/diavoletti/logs/backup.log 2>&1
```

Il job genera un backup ogni notte alle 02:00 e rimuove automaticamente quelli oltre il settimo. Per utilizzare un disco o un mount diverso impostare `BACKUP_DIR`; per modificare la rotazione impostare `BACKUP_RETENTION_COUNT`.

Prima della pubblicazione configurare anche una copia esterna cifrata dei backup. Conservare soltanto i backup sullo stesso server protegge dagli errori applicativi, ma non dalla perdita completa della macchina.

## HTTPS e rinnovo certificati

Dopo che `APP_DOMAIN` punta al VPS e il deploy ha completato l'avvio bootstrap HTTP, creare il certificato Let’s Encrypt con:

```bash
cd /srv/diavoletti
docker compose --env-file .env -f infrastructure/compose.server.yml run --rm certbot certonly --webroot -w /var/www/certbot --email amministrazione@example.it --agree-tos --no-eff-email -d "$APP_DOMAIN"
docker compose --env-file .env -f infrastructure/compose.server.yml up -d --force-recreate frontend
```

Aprire la porta TCP 443 nel firewall dopo l'emissione e configurare il rinnovo automatico nel crontab dell'utente `deploy`:

```cron
15 3 * * * /bin/sh /srv/diavoletti/infrastructure/scripts/renew_certificates.sh >> /srv/diavoletti/logs/certificates.log 2>&1
```

## Server consigliato

Per il gestionale iniziale usare un VPS europeo con Ubuntu 24.04 LTS, Docker e almeno 4 vCPU, 8 GB di RAM e 80 GB NVMe. Questa configurazione ospita PostgreSQL, backend, frontend, reverse proxy, Redis e il processo programmato delle notifiche senza sovradimensionare l'infrastruttura.

Non esporre PostgreSQL su Internet. Esporre esclusivamente HTTPS tramite reverse proxy, mantenere firewall attivo e attivare gli aggiornamenti di sicurezza. Aggiungere una copia cifrata dei backup su uno storage esterno prima dell'apertura al pubblico.
