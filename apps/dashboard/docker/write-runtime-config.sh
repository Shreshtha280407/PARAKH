#!/bin/sh
# Runs on every container start via nginx:alpine's own
# /docker-entrypoint.d/*.sh convention (executed automatically before
# nginx starts, no custom ENTRYPOINT needed). Regenerates the static
# config.json the dashboard fetches at boot (see src/api.ts's
# loadRuntimeConfig) from an environment variable -- this is what lets one
# built image be redeployed against a different backend origin by only
# changing DASHBOARD_RUNTIME_API_BASE_URL and restarting the container,
# with no rebuild. Leaving it unset keeps the build-time VITE_API_BASE_URL
# default (an empty {} changes nothing, see loadRuntimeConfig).
set -eu

CONFIG_PATH="/usr/share/nginx/html/config.json"

if [ -n "${DASHBOARD_RUNTIME_API_BASE_URL:-}" ]; then
  printf '{"apiBaseUrl":"%s","accessMode":"%s"}\n' "$DASHBOARD_RUNTIME_API_BASE_URL" "${DASHBOARD_ACCESS_MODE:-private}" > "$CONFIG_PATH"
else
  printf '{"accessMode":"%s"}\n' "${DASHBOARD_ACCESS_MODE:-private}" > "$CONFIG_PATH"
fi
