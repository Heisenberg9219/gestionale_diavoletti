#!/bin/sh
set -eu

: "${APP_DOMAIN:?APP_DOMAIN is required}"

certificate="/etc/letsencrypt/live/${APP_DOMAIN}/fullchain.pem"
if [ -f "$certificate" ]; then
    template="/etc/nginx/diavoletti/https.conf.template"
else
    template="/etc/nginx/diavoletti/bootstrap.conf.template"
fi

envsubst '$APP_DOMAIN' < "$template" > /etc/nginx/conf.d/default.conf

exec "$@"
