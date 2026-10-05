# Frontend for Cloud Run (migración completa a GCP). Build context is the repo
# root. Multi-stage with Next standalone output: no node_modules at runtime.
FROM node:22-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN corepack enable && pnpm build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
# Cloud Run injects PORT=8080; pinned here so local runs match the mapping.
ENV PORT=8080
# AGENT_URL is runtime env (set by Terraform to the agent's Cloud Run URL) —
# the same image can point at any environment.
COPY --from=build /app/.next/standalone ./
# Next's standalone output leaves public/ out on purpose: without this line every file in it answers 404 (the logo).
COPY --from=build /app/public ./public
COPY --from=build /app/.next/static ./.next/static
CMD ["node", "server.js"]
