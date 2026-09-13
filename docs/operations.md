# Operazioni di produzione

## Backup PostgreSQL

Lo script `infrastructure/scripts/backup_postgres.py` crea un dump PostgreSQL in formato custom e conserva gli ultimi sette file. I dump sono archiviati in `infrastructure/backups/`, esclusa da Git.

Sul server, eseguire il processo con un utente autorizzato a usare Docker. Per esempio, dopo aver clonato il progetto in `/srv/diavoletti`, aggiungere al crontab:

```cron
0 2 * * * cd /srv/diavoletti && /usr/bin/python3 infrastructure/scripts/backup_postgres.py >> /var/log/diavoletti-backup.log 2>&1
```

Il job genera un backup ogni notte alle 02:00 e rimuove automaticamente quelli oltre il settimo. Per utilizzare un disco o un mount diverso impostare `BACKUP_DIR`; per modificare la rotazione impostare `BACKUP_RETENTION_COUNT`.

Prima della pubblicazione configurare anche una copia esterna cifrata dei backup. Conservare soltanto i backup sullo stesso server protegge dagli errori applicativi, ma non dalla perdita completa della macchina.

## Server consigliato

Per il gestionale iniziale usare un VPS europeo con Ubuntu 24.04 LTS, Docker e almeno 4 vCPU, 8 GB di RAM e 80 GB NVMe. Questa configurazione ospita PostgreSQL, backend, frontend, reverse proxy, Redis e il processo programmato delle notifiche senza sovradimensionare l'infrastruttura.

Non esporre PostgreSQL su Internet. Esporre esclusivamente HTTPS tramite reverse proxy, mantenere firewall attivo e attivare gli aggiornamenti di sicurezza. Aggiungere una copia cifrata dei backup su uno storage esterno prima dell'apertura al pubblico.
