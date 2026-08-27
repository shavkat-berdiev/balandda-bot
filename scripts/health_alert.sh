#!/usr/bin/env bash
#
# Health watchdog for the Balandda booking stack.
#
# Background: on 2026-08-27 a host reboot left the Postgres container down for three hours.
# The API stayed up and /api/health answered 200 throughout, so nothing alerted and the
# booking calendar was found broken by hand. /api/health now queries the database and
# returns 503 when it can't — this script is what turns that into a message someone reads.
#
# Install (on the VPS):
#   sudo install -m 755 health_alert.sh /opt/projects/monitor/health_alert.sh
#   sudo install -m 600 /dev/null /opt/projects/monitor/health_alert.env   # then fill it in
#   crontab -e   →   */3 * * * * /opt/projects/monitor/health_alert.sh >/dev/null 2>&1
#
# health_alert.env:
#   TG_BOT_TOKEN=123456:AA...
#   TG_CHAT_ID=-1001234567890
#   TG_THREAD_ID=            # optional: topic id inside a forum group
#   HEALTH_URLS="https://calendar.balandda.uz/api/health"
#
set -uo pipefail

CONF="${HEALTH_ALERT_ENV:-/opt/projects/monitor/health_alert.env}"
STATE_DIR="${HEALTH_ALERT_STATE:-/var/tmp/balandda-health}"

# Two consecutive failures before shouting: a single dropped packet is not an outage.
FAIL_THRESHOLD="${FAIL_THRESHOLD:-2}"
# While it stays down, repeat the alert this often (seconds) so it can't be forgotten.
REMIND_EVERY="${REMIND_EVERY:-1800}"
CURL_TIMEOUT="${CURL_TIMEOUT:-15}"

[ -r "$CONF" ] || { echo "missing config: $CONF" >&2; exit 1; }

# Anything set in the environment must beat the config file — otherwise a one-off
# `HEALTH_URLS=... ./health_alert.sh` silently checks the configured URL instead, which is
# how a "test" can pass without ever exercising the thing you meant to test.
_env_urls="${HEALTH_URLS:-}"
_env_chat="${TG_CHAT_ID:-}"

# shellcheck disable=SC1090
. "$CONF"

[ -n "$_env_urls" ] && HEALTH_URLS="$_env_urls"
[ -n "$_env_chat" ] && TG_CHAT_ID="$_env_chat"

: "${TG_BOT_TOKEN:?TG_BOT_TOKEN not set}"
: "${TG_CHAT_ID:?TG_CHAT_ID not set}"
HEALTH_URLS="${HEALTH_URLS:-https://calendar.balandda.uz/api/health}"

mkdir -p "$STATE_DIR"

notify() {
  local text="$1"
  local args=(--data-urlencode "chat_id=${TG_CHAT_ID}"
              --data-urlencode "text=${text}"
              --data-urlencode "parse_mode=HTML"
              --data-urlencode "disable_web_page_preview=true")
  [ -n "${TG_THREAD_ID:-}" ] && args+=(--data-urlencode "message_thread_id=${TG_THREAD_ID}")
  curl -sS -m 20 -o /dev/null -X POST \
    "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" "${args[@]}" \
    || echo "telegram notify failed" >&2
}

check_one() {
  local url="$1"
  local key body code
  key="$(printf '%s' "$url" | tr -c 'A-Za-z0-9' '_')"
  local f_count="${STATE_DIR}/${key}.fails"
  local f_alerted="${STATE_DIR}/${key}.alerted"

  body="$(curl -sS -m "$CURL_TIMEOUT" -w $'\n%{http_code}' "$url" 2>/dev/null)" || body=$'\n000'
  code="${body##*$'\n'}"
  body="${body%$'\n'*}"

  local ok=0
  # 200 alone is not enough — the endpoint must also say the database is reachable.
  if [ "$code" = "200" ] && printf '%s' "$body" | grep -q '"status" *: *"ok"'; then
    ok=1
  fi

  local fails=0
  [ -r "$f_count" ] && fails="$(cat "$f_count" 2>/dev/null || echo 0)"

  if [ "$ok" = "1" ]; then
    # Recovered — only announce if we actually complained about it.
    if [ -f "$f_alerted" ]; then
      local since down_for
      since="$(stat -c %Y "$f_alerted" 2>/dev/null || echo 0)"
      down_for=$(( ($(date +%s) - since) / 60 ))
      notify "✅ <b>Восстановлено</b>
${url}
Была недоступна ~${down_for} мин."
      rm -f "$f_alerted"
    fi
    echo 0 > "$f_count"
    return 0
  fi

  fails=$(( fails + 1 ))
  echo "$fails" > "$f_count"
  [ "$fails" -lt "$FAIL_THRESHOLD" ] && return 1

  # Already alerted and the reminder interval hasn't elapsed → stay quiet.
  if [ -f "$f_alerted" ]; then
    local last now
    last="$(cat "$f_alerted" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    [ $(( now - last )) -lt "$REMIND_EVERY" ] && return 1
  fi

  local detail
  detail="$(printf '%s' "$body" | head -c 300)"
  [ -z "$detail" ] && detail="(нет ответа)"
  notify "🔴 <b>Balandda: сервис недоступен</b>
${url}
HTTP: <code>${code}</code>
<code>$(printf '%s' "$detail" | sed 's/[<>&]//g')</code>

Проверить: <code>sudo docker ps -a --filter name=balandda</code>"
  date +%s > "$f_alerted"
  return 1
}

rc=0
for u in $HEALTH_URLS; do
  check_one "$u" || rc=1
done
exit "$rc"
