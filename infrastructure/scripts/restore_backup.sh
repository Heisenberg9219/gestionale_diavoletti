#!/bin/sh
# Ripristina il gestionale da un backup creato da backup_postgres.py.
#
# Uso (dalla cartella del progetto sul server, es. /srv/diavoletti):
#   sh infrastructure/scripts/restore_backup.sh                 # ultimo backup disponibile
#   sh infrastructure/scripts/restore_backup.sh 2026-10-23      # backup di un giorno preciso
#   sh infrastructure/scripts/restore_backup.sh percorso/file.dump [percorso/media.tar.gz]
#
# Cosa fa:
#   1. controlla che il backup sia leggibile (altrimenti non tocca nulla);
#   2. salva lo stato attuale in backups/pre-restore (ultime 3 copie);
#   3. ferma backend e frontend, cancella e ricrea il database e carica il dump;
#   4. ripristina gli allegati (se c'è l'archivio dello stesso giorno);
#   5. applica le migrazioni del codice attuale e riavvia tutto.
#
# Variabili utili: COMPOSE_FILE, COMPOSE_ENV_FILE, BACKUP_DIR, RESTORE_YES=1 (salta la conferma).
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-"$PROJECT_ROOT/infrastructure/compose.server.yml"}
ENV_FILE=${COMPOSE_ENV_FILE:-"$PROJECT_ROOT/.env"}
BACKUP_DIR=${BACKUP_DIR:-"$PROJECT_ROOT/infrastructure/backups"}

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

fail() {
    echo "ERRORE: $*" >&2
    exit 1
}

# --- Scelta dei file -------------------------------------------------------
DUMP=""
MEDIA=""
case "${1:-}" in
    "")
        DUMP=$(ls -1 "$BACKUP_DIR"/diavoletti-[0-9]*.dump 2>/dev/null | sort | tail -n 1 || true)
        ;;
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
        DUMP=$(ls -1 "$BACKUP_DIR"/diavoletti-"$1"*.dump 2>/dev/null | sort | tail -n 1 || true)
        ;;
    *)
        DUMP=$1
        MEDIA=${2:-}
        ;;
esac
[ -n "$DUMP" ] && [ -f "$DUMP" ] || fail "nessun backup del database trovato (${1:-ultimo disponibile})."

if [ -z "$MEDIA" ]; then
    DAY=$(basename "$DUMP" | sed -n 's/^diavoletti-\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/p')
    if [ -n "$DAY" ]; then
        MEDIA=$(ls -1 "$BACKUP_DIR"/diavoletti-media-"$DAY"*.tar.gz 2>/dev/null | sort | tail -n 1 || true)
    fi
fi
if [ -n "$MEDIA" ] && [ ! -f "$MEDIA" ]; then
    fail "archivio allegati non trovato: $MEDIA"
fi

echo "Backup database : $DUMP"
echo "Backup allegati : ${MEDIA:-nessuno (gli allegati attuali restano invariati)}"
echo
echo "ATTENZIONE: il database attuale verrà SOSTITUITO con questo backup."
if [ "${RESTORE_YES:-0}" != "1" ]; then
    printf 'Scrivi RIPRISTINA per continuare: '
    read -r answer
    [ "$answer" = "RIPRISTINA" ] || fail "ripristino annullato."
fi

# --- 1. Verifica del backup prima di toccare il database --------------------
compose up -d --wait db
compose exec -T db pg_restore --list < "$DUMP" | grep -q "TABLE DATA" \
    || fail "il file $DUMP non è un backup valido: database NON modificato."

# --- 2. Copia di sicurezza dello stato attuale (si tengono le ultime 3) -----
SAFETY_DIR="$BACKUP_DIR/pre-restore"
mkdir -p "$SAFETY_DIR"
SAFETY_FILE="$SAFETY_DIR/diavoletti-prima-del-ripristino-$(date +%Y-%m-%d_%H-%M-%S).dump"
if compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-privileges' > "$SAFETY_FILE" 2>/dev/null \
    && [ -s "$SAFETY_FILE" ]; then
    echo "Stato attuale salvato in $SAFETY_FILE"
else
    rm -f "$SAFETY_FILE"
    echo "Database attuale non leggibile: nessuna copia di sicurezza (normale dopo un guasto)."
fi
ls -1t "$SAFETY_DIR"/*.dump 2>/dev/null | tail -n +4 | while read -r old_file; do rm -f "$old_file"; done

# --- 3. Stop applicazione e ripristino database -----------------------------
compose stop backend frontend 2>/dev/null || true
compose exec -T db sh -c '
    dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB" &&
    createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"
'
compose exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error' < "$DUMP" \
    || fail "caricamento del dump non riuscito. La copia dello stato precedente è in $SAFETY_DIR."
echo "Database ripristinato."

# --- 4. Allegati -------------------------------------------------------------
if [ -n "$MEDIA" ]; then
    compose run --rm --no-deps -T backend sh -c 'mkdir -p /app/media && tar -C /app/media -xzf -' < "$MEDIA"
    echo "Allegati ripristinati."
fi

# --- 5. Migrazioni e riavvio -------------------------------------------------
compose run --rm --no-deps backend python manage.py migrate --noinput
compose up -d
echo
echo "Ripristino completato. Controlla il gestionale."
