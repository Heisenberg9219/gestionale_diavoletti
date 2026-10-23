# Operazioni di produzione

## Backup PostgreSQL

Lo script `infrastructure/scripts/backup_postgres.py` crea un dump PostgreSQL in formato custom e un archivio `diavoletti-media-*.tar.gz` con gli allegati caricati (fatture, ricevute), conservando gli ultimi sette di ciascun tipo. Per saltare gli allegati impostare `BACKUP_MEDIA=false`. Il deploy esegue automaticamente un backup prima di applicare le migrazioni. I dump sono archiviati in `infrastructure/backups/`, esclusa da Git.

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

## OCR delle fatture

L'analisi OCR usa Azure AI Document Intelligence con il modello `prebuilt-invoice`.
Nel repository GitHub, per ciascun ambiente, configurare:

- variabile `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`: endpoint della risorsa Azure, ad esempio `https://nome-risorsa.cognitiveservices.azure.com/`;
- secret `AZURE_DOCUMENT_INTELLIGENCE_KEY`: una delle chiavi della stessa risorsa.

La pipeline scrive entrambi i valori nel file `.env` del server durante il deploy. Non inserire la chiave nel repository o direttamente nel file versionato.

## Server consigliato

Per il gestionale iniziale usare un VPS europeo con Ubuntu 24.04 LTS, Docker e almeno 4 vCPU, 8 GB di RAM e 80 GB NVMe. Questa configurazione ospita PostgreSQL, backend, frontend, reverse proxy, Redis e il processo programmato delle notifiche senza sovradimensionare l'infrastruttura.

Non esporre PostgreSQL su Internet. Esporre esclusivamente HTTPS tramite reverse proxy, mantenere firewall attivo e attivare gli aggiornamenti di sicurezza. Aggiungere una copia cifrata dei backup su uno storage esterno prima dell'apertura al pubblico.

## Deploy

Il workflow `Build and deploy` esegue prima i test (`.github/workflows/tests.yml`), poi sul server:

1. backup di database e allegati (se il database è già attivo);
2. build delle nuove immagini, con la versione precedente ancora in linea;
3. `migrate` e `collectstatic` in container temporanei: se falliscono il deploy si interrompe e resta attiva la versione precedente;
4. avvio della nuova versione.

I valori di variabili e secret non possono contenere apici singoli, a capo o iniziare con `$`: il workflow si ferma con un messaggio esplicito.

## Allegati protetti

Fatture e ricevute non sono più raggiungibili all'indirizzo pubblico `/media/`. Si scaricano da `/api/v1/documents/attachments/<id>/download/` e `/api/v1/expenses/attachments/<id>/download/`, che verificano l'utente; in produzione nginx invia il file tramite `X-Accel-Redirect` dalla location interna `/protected-media/`. Sono accettati solo PDF, JPG e PNG fino a 20 MB, salvati con nome casuale.

## Sicurezza HTTPS

Django riconosce HTTPS tramite l'header `X-Forwarded-Proto` impostato da nginx e accetta il login dell'admin dall'origine `https://APP_DOMAIN`. HSTS è disattivato per default: quando il certificato e il rinnovo automatico sono stabili, impostare `DJANGO_HSTS_SECONDS=31536000` (aggiungendo la variabile al file `.env` generato dal workflow di deploy).
