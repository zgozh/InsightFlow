#!/bin/sh
set -eu

# Windows bind mounts do not preserve the private mode PostgreSQL requires for
# a server key. Copy it into the container and set ownership/mode before the
# official entrypoint drops privileges and initializes the persistent volume.
install -o postgres -g postgres -m 0644 /run/analytics-demo-tls/server.crt /tmp/analytics-demo-server.crt
install -o postgres -g postgres -m 0600 /run/analytics-demo-tls/server.key /tmp/analytics-demo-server.key
exec docker-entrypoint.sh "$@"
