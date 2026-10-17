FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite inlines import.meta.env.* at build time -- this must be set before
# `npm run build`, a runtime env var on the container would be too late.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# P10: regenerates config.json from $DASHBOARD_RUNTIME_API_BASE_URL on
# every container start (nginx:alpine runs every executable script here
# automatically before starting nginx) -- see docker/write-runtime-config.sh
# and src/api.ts's loadRuntimeConfig for why this lets one built image
# serve different deployments without a rebuild.
COPY docker/write-runtime-config.sh /docker-entrypoint.d/20-write-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/20-write-runtime-config.sh
EXPOSE 80
