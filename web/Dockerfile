FROM node:24-bookworm-slim AS deps

WORKDIR /app

COPY web/package.json web/pnpm-lock.yaml /app/

RUN corepack enable \
    && corepack prepare pnpm@10.18.3 --activate \
    && pnpm install --frozen-lockfile

FROM node:24-bookworm-slim AS builder

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL=http://127.0.0.1:8080
ENV NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL=${NEXT_PUBLIC_PROOF_OF_AUDIT_API_URL}

COPY --from=deps /app/node_modules /app/node_modules
COPY web /app

RUN corepack enable \
    && corepack prepare pnpm@10.18.3 --activate \
    && pnpm build

FROM node:24-bookworm-slim AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV HOSTNAME=0.0.0.0
ENV PORT=8080

COPY --from=builder /app/public /app/public
COPY --from=builder /app/.next/standalone /app/
COPY --from=builder /app/.next/static /app/.next/static

EXPOSE 8080

CMD ["node", "server.js"]
