FROM nginx:1.27-alpine

# Clean default HTML and add curl for healthchecks
RUN rm -rf /usr/share/nginx/html/* \
    && apk add --no-cache curl

# Static UI + reverse-proxy config
COPY public/ /usr/share/nginx/html/
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# Healthcheck THROUGH the proxy to the controller
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1/api/healthz > /dev/null || exit 1

EXPOSE 80
