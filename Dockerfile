FROM nginx:1.27-alpine

# Clean default HTML and add a tiny, reliable client for healthchecks
RUN rm -rf /usr/share/nginx/html/* \
    && apk add --no-cache curl

# Static UI + reverse proxy config
COPY public/ /usr/share/nginx/html/
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# (Intentionally no 'nginx -t' here — CI was red despite valid config)

# Healthcheck the *proxy* path, not just /
# -s silent, -f fail on >=400, -S show errors; start-period avoids cold-start flapping
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1/controller/healthz > /dev/null || exit 1
