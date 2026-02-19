#!/usr/bin/env bash
set -euo pipefail
docker stop tgi-med42 >/dev/null 2>&1 || true
echo "Stopped container: tgi-med42"