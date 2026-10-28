# syntax=docker/dockerfile:1
# Node.js and pnpm are build-time only; the final image serves static files with Caddy and has no
# Node.js runtime (ADR-0001 Constraint 1, ADR-0001-C5; ADR-0004 *Composition and placement*).

FROM node:22.23.4-alpine3.24 AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
# The pnpm version comes from the manifest's packageManager field, so it is pinned in one place.
RUN npm install --global "$(node -p "require('./package.json').packageManager")" \
 && pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Same pinned Caddy release as `proxy`.
FROM caddy:2.11.7
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
USER nobody
EXPOSE 8080
