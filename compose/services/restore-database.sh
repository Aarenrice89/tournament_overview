#!/bin/bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <s3-key> [restore command options]" >&2
  exit 2
fi

if [ "${DATABASE_RESTORE_LOCK_HELD:-}" != "true" ]; then
  export DATABASE_RESTORE_LOCK_HELD=true
  exec flock /var/lock/midtnvbc-database-backup.lock "$0" "$@"
fi

compose=(docker compose --env-file compose/envs/.env.production -f compose/docker-compose.production.yml)
restore_key="$1"
shift

"${compose[@]}" stop api
if ! "${compose[@]}" run --rm --no-deps api python manage.py restore_database_backup "$restore_key" --confirm-replace-database --allow-production-restore "$@"; then
  echo "Restore failed; API remains stopped." >&2
  exit 1
fi
"${compose[@]}" up -d api
