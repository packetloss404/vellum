# Multi-platform index digests recorded 2026-09-04. Keep the readable tag so
# automated dependency tooling can propose intentional digest updates.
FROM node:26.11.1-alpine@sha256:143494b1da2945f061539253adc65e4f1569ddf07da2d384c022c791a9d90a4a AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.29.4-alpine@sha256:4870c12cd2ca986de501a804b4f506ad3875a0b1874940ba0a2c7f763f1855b2
COPY --from=build /app/dist /usr/share/nginx/html
COPY docs/index.html /usr/share/nginx/html/docs/index.html
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
