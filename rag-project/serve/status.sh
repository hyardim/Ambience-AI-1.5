#!/usr/bin/env bash
set -euo pipefail

echo "== Container =="
docker ps --filter "name=tgi-med42" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

echo
echo "== Health =="
curl -s -o /dev/null -w "HTTP %{http_code}\n" 127.0.0.1:80/health || true

echo
echo "== Quick generate =="
curl -s 127.0.0.1:80/generate \
  -X POST -H 'Content-Type: application/json' \
  -d '{"inputs":"Say hello in one sentence.","parameters":{"max_new_tokens":32}}' \
  | head -c 240
echo
