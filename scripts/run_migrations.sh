#!/usr/bin/env bash
#
# Apply every migrations/*.sql file to a D1 database and fail on real errors.
#
# Usage:
#   scripts/run_migrations.sh <database-name> <wrangler-config> --remote|--local
#
# Examples:
#   scripts/run_migrations.sh planetcf wrangler.production.jsonc --remote
#   scripts/run_migrations.sh test-planet-db examples/test-planet/wrangler.jsonc --remote
#
# These migrations are not tracked by `wrangler d1 migrations`, so every file is
# executed on every run. Re-running a migration that is already applied fails
# with a known message ("already exists" for CREATE, "duplicate column name" for
# ALTER TABLE ... ADD COLUMN), and only those failures are treated as
# "already applied". Pass/fail comes from wrangler's exit code; the output is
# only read to classify a failure as one of those benign re-run errors.
#
# Any other failure (bad token, network, SQL error, missing table, ...) stops
# here with a non-zero exit status, so a deploy step that follows never runs.

set -uo pipefail

usage() {
    echo "Usage: $0 <database-name> <wrangler-config> --remote|--local" >&2
}

if [[ $# -ne 3 ]]; then
    usage
    exit 2
fi

DB_NAME="$1"
CONFIG_FILE="$2"
LOCATION="$3"

case "$LOCATION" in
    --remote|--local) ;;
    *)
        usage
        exit 2
        ;;
esac

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: wrangler config not found: $CONFIG_FILE" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="$(dirname "$SCRIPT_DIR")/migrations"

# Errors that mean "this migration was applied on an earlier run".
BENIGN_RERUN_ERRORS='already exists|duplicate column name'

shopt -s nullglob
MIGRATIONS=("$MIGRATIONS_DIR"/*.sql)
if [[ ${#MIGRATIONS[@]} -eq 0 ]]; then
    echo "Error: no migrations found in $MIGRATIONS_DIR" >&2
    exit 1
fi

for migration in "${MIGRATIONS[@]}"; do
    name="$(basename "$migration")"
    if output="$(npx wrangler d1 execute "$DB_NAME" "$LOCATION" --config "$CONFIG_FILE" --file "$migration" 2>&1)"; then
        echo "Applied: $name"
    elif grep -qiE "$BENIGN_RERUN_ERRORS" <<<"$output"; then
        echo "Already applied: $name"
    else
        echo "$output"
        echo "::error::Migration $name failed against $DB_NAME; stopping before any later migration or deploy."
        exit 1
    fi
done

echo "Migrations complete for $DB_NAME"
