#!/usr/bin/env sh
set -eu

BASE_URL="${1:-${VELLUM_BASE_URL:-https://vellum.ianlan.dev}}"

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
request_status 200 "$BASE_URL/"
request_status 200 "$BASE_URL/docs/"
request_status 200 "$BASE_URL/api/dossiers"

headers="$(curl --fail --silent --show-error --head "$BASE_URL/")"
echo "$headers" | grep -qi '^content-security-policy:' || {
    echo "FAIL: Content-Security-Policy header missing" >&2
    exit 1
}
if [ "${VELLUM_REQUIRE_HSTS:-false}" = "true" ]; then
    echo "$headers" | grep -qi '^strict-transport-security:' || {
        echo "FAIL: Strict-Transport-Security header missing" >&2
        exit 1
    }
elif ! echo "$headers" | grep -qi '^strict-transport-security:'; then
    echo "note: Strict-Transport-Security is not enabled at the edge"
fi

echo "Vellum public-route smoke checks passed."
