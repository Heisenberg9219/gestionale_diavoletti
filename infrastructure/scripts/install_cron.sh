#!/bin/sh
# Installa (o aggiorna) le attività pianificate del gestionale nel crontab
# dell'utente che lo esegue (sul server: l'utente "deploy").
#
#   sh infrastructure/scripts/install_cron.sh
#
# Attività:
#   02:00  backup giornaliero di database e allegati (si tengono 7 giorni)
#   03:15  rinnovo dei certificati HTTPS
#   07:00  avvisi su spese, buoni, liste regalo e riordini
#
# Si può rilanciare senza problemi: sostituisce le righe installate in precedenza.
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/infrastructure/compose.server.yml"
ENV_FILE="$PROJECT_ROOT/.env"
LOG_DIR="$PROJECT_ROOT/logs"
PYTHON=$(command -v python3 || true)
DOCKER=$(command -v docker || true)
MARKER="# diavoletti"

[ -n "$PYTHON" ] || { echo "ERRORE: python3 non trovato." >&2; exit 1; }
[ -n "$DOCKER" ] || { echo "ERRORE: docker non trovato." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERRORE: manca $ENV_FILE" >&2; exit 1; }
mkdir -p "$LOG_DIR"

COMPOSE="$DOCKER compose --env-file '$ENV_FILE' -f '$COMPOSE_FILE'"
CRON_PATH="PATH=$(dirname "$DOCKER"):/usr/local/bin:/usr/bin:/bin"

NEW_LINES=$(cat <<EOF
0 2 * * * $CRON_PATH COMPOSE_FILE='$COMPOSE_FILE' COMPOSE_ENV_FILE='$ENV_FILE' $PYTHON '$PROJECT_ROOT/infrastructure/scripts/backup_postgres.py' >> '$LOG_DIR/backup.log' 2>&1 $MARKER backup
15 3 * * * $CRON_PATH /bin/sh '$PROJECT_ROOT/infrastructure/scripts/renew_certificates.sh' >> '$LOG_DIR/certificates.log' 2>&1 $MARKER certificati
0 7 * * * $CRON_PATH $COMPOSE exec -T backend python manage.py generate_notifications >> '$LOG_DIR/notifications.log' 2>&1 $MARKER notifiche
EOF
)

CURRENT=$(crontab -l 2>/dev/null || true)
# Rimuove le righe del gestionale installate prima (marcate) e le vecchie righe
# manuali che richiamano gli stessi script, così non si duplicano.
KEPT=$(printf '%s\n' "$CURRENT" | grep -v "$MARKER" | grep -v "backup_postgres.py" | grep -v "renew_certificates.sh" | grep -v "generate_notifications" || true)

printf '%s\n%s\n' "$KEPT" "$NEW_LINES" | sed '/^$/d' | crontab -
echo "Attività pianificate installate:"
crontab -l | grep "$MARKER"
