#!/bin/sh
# Daily database backup. Run from a scheduler (cron / Render cron job). Keeps the last 14 copies.
# Needs DATABASE_URL (plain postgresql://... form) and pg_dump installed.
set -e
mkdir -p backups
pg_dump "$DATABASE_URL" | gzip > "backups/flowmate-$(date +%F).sql.gz"
ls -1t backups/flowmate-*.sql.gz | tail -n +15 | xargs -r rm
echo "Backup done"
