#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
FULLCHAIN_PATH="$CERT_DIR/fullchain.pem"
PRIVKEY_PATH="$CERT_DIR/privkey.pem"

if [ -s "$FULLCHAIN_PATH" ] && [ -s "$PRIVKEY_PATH" ]; then
  echo "nginx: using mounted TLS certificate files"
  exit 0
fi

if [ "${NGINX_GENERATE_SELF_SIGNED:-true}" != "true" ]; then
  echo "nginx: missing TLS cert files and self-signed generation is disabled"
  echo "nginx: provide nginx/certs/fullchain.pem and nginx/certs/privkey.pem"
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "nginx: openssl is required to generate fallback certificates"
  exit 1
fi

mkdir -p "$CERT_DIR"

echo "nginx: generating fallback self-signed certificate"
openssl req \
  -x509 \
  -nodes \
  -newkey rsa:2048 \
  -days "${NGINX_SELF_SIGNED_DAYS:-30}" \
  -keyout "$PRIVKEY_PATH" \
  -out "$FULLCHAIN_PATH" \
  -subj "${NGINX_SELF_SIGNED_SUBJECT:-/CN=localhost}" \
  >/dev/null 2>&1

chmod 600 "$PRIVKEY_PATH"
chmod 644 "$FULLCHAIN_PATH"
