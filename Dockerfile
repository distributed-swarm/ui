FROM nginx:1.27-alpine

# Basic tools (curl is handy for smoke tests)
RUN rm -rf /usr/share/nginx/html/* \
    && apk add --no-cache curl

# Static UI (build artifact lives in public/)
COPY public/ /usr/share/nginx/html/

# Default API upstream:
# - In swarm / docker network: controller resolves by DNS name "controller"
# - Override at runtime with:  -e API_UPSTREAM=http://host.docker.internal:8080
ENV API_UPSTREAM=http://controller:8080

# Use nginx envsubst templating (processed at container start by nginx entrypoint)
# This will generate: /etc/nginx/conf.d/default.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
