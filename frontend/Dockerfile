# Stage 1: Dependencies
FROM node:26-alpine AS deps
LABEL keep-cache="true"
RUN apk upgrade --no-cache
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Stage 2: Build
FROM deps AS build
LABEL keep-cache="false"
COPY . .
# Vite reads .env.production automatically when running `build`.
# The deploy workflow writes /frontend/.env from the FRONTEND_ENV secret before build.
RUN npm run build
