FROM node:22-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export npm_config_cafile=/run/secrets/build_ca_bundle; fi; \
    npm ci --no-audit --no-fund
FROM dependencies AS build
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine
COPY --chown=101:101 nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080 8443
ENTRYPOINT ["nginx", "-g", "daemon off;"]
