#!/bin/bash

# === CONFIG ===
DB_NAME="mia2"
DB_USER="postgres"
BACKUP_DIR="/var/backups/postgres"
DATE=$(date +"%Y-%m-%d_%H-%M")
FILENAME="$BACKUP_DIR/${DB_NAME}_backup_$DATE.sql.gz"

# Ensure backup directory exists
mkdir -p $BACKUP_DIR

# Export password (skip if using peer auth or .pgpass)
# export PGPASSWORD=your_password

# Dump and compress the database
sudo -u postgres pg_dump $DB_NAME | gzip > "$FILENAME"

# Keep only last 7 backups
find $BACKUP_DIR -type f -name "${DB_NAME}_backup_*.sql.gz" -mtime +7 -delete

# Optional: Logging
echo "[pg_backup] $(date) Backup created: $FILENAME"

# === Optional: Reindex IVFFlat indexes and analyze ===
sudo -u postgres psql -d $DB_NAME <<EOF
REINDEX INDEX CONCURRENTLY tags_vector_idx;
REINDEX INDEX CONCURRENTLY swatch_vector_idx;
ANALYZE data;
EOF

echo "[Pg_backup] $(date) Reindex + Analyze completed"