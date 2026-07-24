#!/bin/bash
# Billz endpoint probe — run on VPS: ssh user@83.69.135.27 'bash -s' < scripts/billz_probe.sh
set -u

KEY=$(grep -oP '^BILLZ_API_KEY=\K.*' /opt/projects/blndtgskladbot/.env | tr -d '\r')
echo "key_len=${#KEY}"

TOKEN=$(curl -s -X POST https://api-admin.billz.ai/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"secret_token\":\"$KEY\"}" | grep -oP '"access_token":"\K[^"]*' | head -1)
echo "token_len=${#TOKEN}"

D=$(date -d yesterday +%F)
ENDPOINTS=(
  "/v2/orders?date_from=$D&date_to=$D&limit=10"
  "/v2/orders?date_begin=$D&date_end=$D&limit=10"
  "/v1/orders?date_begin=$D&date_end=$D&limit=10"
  "/v1/report/sales?date_begin=$D&date_end=$D"
  "/v2/report/sales?date_begin=$D&date_end=$D"
  "/v1/report/product-sales?date_begin=$D&date_end=$D"
  "/v2/reports/sales?date_begin=$D&date_end=$D"
)
for ep in "${ENDPOINTS[@]}"; do
  CODE=$(curl -s -o /tmp/bp.json -w '%{http_code}' "https://api-admin.billz.ai$ep" -H "Authorization: Bearer $TOKEN")
  echo "== $CODE $ep"
  if [ "$CODE" = "200" ]; then
    head -c 500 /tmp/bp.json
    echo
  fi
done

echo "--- analytics .env tail:"
tail -c 150 /opt/projects/analytics/.env; echo
