#!/usr/bin/env bash
set -e

URL="http://127.0.0.1:80/health"

echo "Waiting for TGI to become healthy..."

while true; do
  if curl -sf "$URL" > /dev/null; then
    echo "✅ TGI is healthy."
    exit 0
  fi
  echo "⏳ still starting..."
  sleep 5
done
