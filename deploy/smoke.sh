#!/usr/bin/env sh
set -eu

BASE_URL="${1:-${VELLUM_BASE_URL:-https://vellum.ianlan.dev}}"
: "${VELLUM_SMOKE_USER:?set VELLUM_SMOKE_USER for the Caddy login}"
: "${VELLUM_SMOKE_PASSWORD:?set VELLUM_SMOKE_PASSWORD for the Caddy login}"

AUTH_CONFIG="$(mktemp)"
trap 'rm -f "$AUTH_CONFIG"' EXIT HUP INT TERM
chmod 600 "$AUTH_CONFIG"
escaped_user="$(printf '%s' "$VELLUM_SMOKE_USER" | sed 's/\\/\\\\/g; s/"/\\"/g')"
escaped_password="$(printf '%s' "$VELLUM_SMOKE_PASSWORD" | sed 's/\\/\\\\/g; s/"/\\"/g')"
printf 'user = "%s:%s"\n' "$escaped_user" "$escaped_password" > "$AUTH_CONFIG"
unset escaped_user escaped_password

request_status() {
    expected="$1"
    url="$2"
    shift 2
    actual="$(curl --fail-with-body --silent --show-error --output /dev/null \
        --write-out '%{http_code}' "$@" "$url" 2>/dev/null || true)"
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $url returned ${actual:-no-response}; expected $expected" >&2
        exit 1
    fi
    echo "ok: $url -> $actual"
}

request_status 200 "$BASE_URL/health"
request_status 200 "$BASE_URL/ready"
request_status 401 "$BASE_URL/"
request_status 200 "$BASE_URL/" --config "$AUTH_CONFIG"
request_status 200 "$BASE_URL/docs/" --config "$AUTH_CONFIG"
request_status 200 "$BASE_URL/api/dossiers" --config "$AUTH_CONFIG"

headers="$(curl --fail --silent --show-error --config "$AUTH_CONFIG" --head "$BASE_URL/")"
echo "$headers" | grep -qi '^content-security-policy:' || {
    echo "FAIL: Content-Security-Policy header missing" >&2
    exit 1
}
echo "$headers" | grep -qi '^strict-transport-security:' || {
    echo "FAIL: Strict-Transport-Security header missing" >&2
    exit 1
}

echo "Vellum public-route smoke checks passed."
