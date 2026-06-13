#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"

echo "Checking backend at ${API_BASE_URL}"

curl_json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" "${API_BASE_URL}${path}" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -fsS -X "$method" "${API_BASE_URL}${path}"
  fi
}

echo "1. health"
curl_json GET /health >/dev/null

echo "2. models"
curl_json GET /models >/dev/null

echo "3. personas"
curl_json GET /personas >/dev/null

echo "4. councils"
curl_json GET /councils >/dev/null

echo "5. create research post"
created="$(
  curl_json POST /posts \
    '{"content":"Smoke test: critique world models for healthcare research. What assumptions are weak?","council_id":"research"}'
)"
post_id="$(python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])' <<<"$created")"

echo "6. load post ${post_id}"
curl_json GET "/posts/${post_id}" >/dev/null

echo "7. simulate comments"
curl_json POST "/posts/${post_id}/simulate" >/dev/null

echo "8. simulate replies"
curl_json POST "/posts/${post_id}/simulate-reply" >/dev/null

echo "9. continue discussion"
curl_json POST "/posts/${post_id}/continue" >/dev/null

echo "10. export markdown"
curl -fsS "${API_BASE_URL}/posts/${post_id}/export.md" | grep -q "# Local Friend Chat Thread"

echo "Smoke test passed for post ${post_id}"
