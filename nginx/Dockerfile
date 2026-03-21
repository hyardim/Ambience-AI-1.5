FROM nginx:alpine

RUN apk add --no-cache openssl

COPY docker-entrypoint.d/40-ensure-certs.sh /docker-entrypoint.d/40-ensure-certs.sh
RUN chmod +x /docker-entrypoint.d/40-ensure-certs.sh
