# Multi-platform index digests recorded 2026-09-04. Keep the readable tag so
# automated dependency tooling can propose intentional digest updates.
FROM node:22.20.0-alpine@sha256:dbcedd8aeab47fbc0f4dd4bffa55b7c3c729a707875968d467aaaea42d6225af AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.31.0-alpine@sha256:2f07d83bf561b506400dc183b1b2003803e39efbd22451f848adaba14d28c7c7
COPY --from=build /app/dist /usr/share/nginx/html
COPY docs/index.html /usr/share/nginx/html/docs/index.html
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
