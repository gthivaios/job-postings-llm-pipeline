#!/bin/sh
# Export the raw_portals DB as init scripts:
#   02_raw_schema.sql   table definitions
#   03_raw_seed.sql.gz  data
# Output goes to /dumps (./dumps on the host); move the files into docker/mariadb/init/.
set -eu
OPTS="-uroot -p$MARIADB_ROOT_PASSWORD --default-character-set=utf8mb4 --skip-comments
      --skip-dump-date --no-create-db --databases raw_portals"

mariadb-dump $OPTS --no-data > /dumps/02_raw_schema.sql
mariadb-dump $OPTS --no-create-info --order-by-primary | gzip -n -9 > /dumps/03_raw_seed.sql.gz
ls -lh /dumps
