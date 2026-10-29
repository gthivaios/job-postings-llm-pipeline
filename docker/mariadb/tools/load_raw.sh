#!/bin/sh
# Load every raw dump in /raw_dumps (*.sql or *.sql.gz) into raw_portals.
# Maintainer-only: used once to build the public sample.
set -eu
for f in /raw_dumps/*.sql /raw_dumps/*.sql.gz; do
  [ -e "$f" ] || continue
  echo "loading $f"
  case "$f" in
    *.gz) gunzip -c "$f" ;;
    *) cat "$f" ;;
  esac | mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --default-character-set=utf8mb4 raw_portals
done
mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" -N -e \
  "SELECT table_name, table_rows FROM information_schema.tables WHERE table_schema='raw_portals'"
