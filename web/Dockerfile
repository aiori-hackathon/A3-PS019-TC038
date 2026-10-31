# PrivacyTwin web UI (Next.js). Build context: the web/ directory.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# The /api proxy target is fixed at build time. Railway passes service variables as build args.
ARG PRIVACYTWIN_API_URL
ENV PRIVACYTWIN_API_URL=${PRIVACYTWIN_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

FROM node:22-slim
WORKDIR /app
# next.config.ts is loaded again at startup and checks this value.
ARG PRIVACYTWIN_API_URL
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 PRIVACYTWIN_API_URL=${PRIVACYTWIN_API_URL}
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.ts ./
USER node
EXPOSE 3000
# next start reads PORT from the environment.
CMD ["node", "node_modules/next/dist/bin/next", "start"]
