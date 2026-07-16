#!/usr/bin/env bash
set -euo pipefail

# Provision Metabase: create admin user and connect the warehouse.
# Run after Metabase is healthy:
#   docker compose exec metabase /bin/sh -c "apk add curl && sh /setup.sh"
# Or from the host:
#   bash metabase/setup.sh

MB_HOST="${MB_HOST:-http://localhost:3000}"
MB_EMAIL="${MB_ADMIN_EMAIL:-admin@reckon.local}"
MB_PASS="${MB_ADMIN_PASSWORD:-Reckon123!}"
MB_FIRST="${MB_FIRST_NAME:-Reckon}"
MB_LAST="${MB_LAST_NAME:-Admin}"

PG_HOST="${MB_PG_HOST:-warehouse}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DB:-reckon}"
PG_USER="${POSTGRES_USER:-reckon}"
PG_PASS="${POSTGRES_PASSWORD:-reckon_dev}"

echo "Waiting for Metabase to be ready..."
for i in $(seq 1 60); do
  if curl -sf "${MB_HOST}/api/health" | grep -q '"status":"ok"'; then
    echo "Metabase is ready."
    break
  fi
  sleep 5
done

# Get the setup token
SETUP_TOKEN=$(curl -sf "${MB_HOST}/api/session/properties" \
  | grep -o '"setup-token":"[^"]*"' \
  | head -1 \
  | cut -d'"' -f4)

if [ -z "$SETUP_TOKEN" ]; then
  echo "No setup token found. Metabase may already be configured."
  exit 0
fi

echo "Running first-time setup..."
curl -sf "${MB_HOST}/api/setup" \
  -H "Content-Type: application/json" \
  -d "{
    \"token\": \"${SETUP_TOKEN}\",
    \"user\": {
      \"email\": \"${MB_EMAIL}\",
      \"password\": \"${MB_PASS}\",
      \"first_name\": \"${MB_FIRST}\",
      \"last_name\": \"${MB_LAST}\",
      \"site_name\": \"Reckon BI\"
    },
    \"database\": {
      \"engine\": \"postgres\",
      \"name\": \"Reckon Warehouse\",
      \"details\": {
        \"host\": \"${PG_HOST}\",
        \"port\": ${PG_PORT},
        \"dbname\": \"${PG_DB}\",
        \"user\": \"${PG_USER}\",
        \"password\": \"${PG_PASS}\"
      }
    },
    \"prefs\": {
      \"site_name\": \"Reckon BI\",
      \"allow_tracking\": false
    }
  }" > /dev/null

echo "Metabase setup complete."
echo "  Admin: ${MB_EMAIL}"
echo "  URL: ${MB_HOST}"
echo "  Warehouse connection: ${PG_DB}@${PG_HOST}:${PG_PORT}"
