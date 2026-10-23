# Operazioni di produzione

## Attività pianificate (backup, certificati, avvisi)

Sul server, con l'utente `deploy`, dalla cartella del progetto:

```bash
cd /srv/diavoletti
sh infrastructure/scripts/install_cron.sh
```

Lo script installa (o aggiorna, senza duplicare) nel crontab:

| Ora (orario del server) | Attività | Log |
|---|---|---|
| 02:00 | backup di database e allegati | `logs/backup.log` |
| 03:15 | rinnovo certificati HTTPS | `logs/certificates.log` |
| 07:00 | avvisi su spese, buoni, liste regalo e riordini | `logs/notifications.log` |

Gli avvisi sui prodotti esauriti sono immediati e non dipendono dal cron.

## Backup

`infrastructure/scripts/backup_postgres.py` salva in `infrastructure/backups/`:

- `diavoletti-AAAA-MM-GG.dump`: tutto il database (formato custom di PostgreSQL), verificato con `pg_restore --list` subito dopo la creazione;
- `diavoletti-media-AAAA-MM-GG.tar.gz`: gli allegati caricati (fatture, ricevute).

Si tiene **un backup per giorno per gli ultimi 7 giorni**: il giorno più vecchio viene eliminato automaticamente. Se lo script gira più volte nello stesso giorno (cron e deploy) il file del giorno viene sostituito dal più recente. Un backup non riuscito o illeggibile non sostituisce quello precedente.

Backup manuale in qualsiasi momento:

```bash
cd /srv/diavoletti
COMPOSE_FILE=infrastructure/compose.server.yml python3 infrastructure/scripts/backup_postgres.py
ls -lh infrastructure/backups
```

I backup restano sullo stesso server: proteggono da errori e dati danneggiati, non dalla perdita della macchina. Per il disaster recovery copiare regolarmente la cartella `infrastructure/backups` (e il file `.env`) su uno spazio esterno.

## Ripristino

```bash
cd /srv/diavoletti
sh infrastructure/scripts/restore_backup.sh              # ultimo backup
sh infrastructure/scripts/restore_backup.sh 2026-10-21   # backup di un giorno preciso
```

Lo script chiede di scrivere `RIPRISTINA`, poi:

1. controlla che il backup sia leggibile (se non lo è si ferma senza toccare nulla);
2. salva lo stato attuale in `infrastructure/backups/pre-restore/` (ultime 3 copie);
3. ferma backend e frontend, ricrea il database e carica il dump;
4. ripristina gli allegati dello stesso giorno;
5. applica le migrazioni del codice attuale e riavvia tutto.

### Disaster recovery su un server nuovo

1. Installare Docker, clonare il repository in `/srv/diavoletti` sul branch giusto e copiare il file `.env` salvato.
2. Copiare i file di backup in `/srv/diavoletti/infrastructure/backups/`.
3. Avviare il database: `docker compose --env-file .env -f infrastructure/compose.server.yml up -d --wait db`
4. Ripristinare: `sh infrastructure/scripts/restore_backup.sh` (lo script avvia anche backend e frontend, ricostruendo le immagini se mancano).
5. Reinstallare le attività pianificate: `sh infrastructure/scripts/install_cron.sh`.

## HTTPS e rinnovo certificati

Dopo che `APP_DOMAIN` punta al VPS e il deploy ha completato l'avvio bootstrap HTTP, creare il certificato Let’s Encrypt con:

```bash
cd /srv/diavoletti
docker compose --env-file .env -f infrastructure/compose.server.yml run --rm certbot certonly --webroot -w /var/www/certbot --email amministrazione@example.it --agree-tos --no-eff-email -d "$APP_DOMAIN"
docker compose --env-file .env -f infrastructure/compose.server.yml up -d --force-recreate frontend
```

Aprire la porta TCP 443 nel firewall dopo l'emissione. Il rinnovo automatico è installato da `infrastructure/scripts/install_cron.sh` (vedi "Attività pianificate").

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
