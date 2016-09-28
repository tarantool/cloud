#!/bin/sh

if [ -z ${PROMETHEUS_PASSWORD+x} ]
then
    echo ERROR: PROMETHEUS_PASSWORD is not set
    exit 1
fi

echo "prometheus:$(openssl passwd -apr1 $PROMETHEUS_PASSWORD)" > /etc/nginx/htpasswd

exec "$@"
