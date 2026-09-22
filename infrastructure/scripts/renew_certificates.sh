#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-"$PROJECT_ROOT/infrastructure/compose.server.yml"}
ENV_FILE=${COMPOSE_ENV_FILE:-"$PROJECT_ROOT/.env"}

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm certbot renew --quiet
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T frontend nginx -s reload
