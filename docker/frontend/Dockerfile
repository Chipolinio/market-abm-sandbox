# Multi-stage frontend build (Spec 007 §7.4).
FROM node:22-alpine AS builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Same-origin in production: Nginx proxies /api → backend.
ENV VITE_API_BASE_URL=
ENV VITE_WS_BASE_URL=

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /app/frontend/dist /usr/share/nginx/html
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
