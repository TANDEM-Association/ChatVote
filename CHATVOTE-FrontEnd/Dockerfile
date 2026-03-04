# ---------- BUILD ----------
  FROM node:20-alpine AS builder

  WORKDIR /app
  
# Activate corepack and install pnpm
  RUN corepack enable \
  && for i in 1 2 3 4 5; do corepack prepare pnpm@latest --activate && break || sleep 5; done \
  || (echo "pnpm@latest not available, fallback pnpm@10.19.0" && corepack prepare pnpm@10.19.0 --activate)
  
  # Copy only the necessary files for installation
  COPY package.json pnpm-lock.yaml ./
  
  # Install dependencies with pnpm (lockfile strict)
  RUN pnpm install --frozen-lockfile
  
  # Copy the rest of the code
  COPY . .
  
  # Build Next.js app
  RUN pnpm build
  
  # ---------- RUN ----------
  FROM node:20-alpine AS runner
  
  WORKDIR /app
  ENV NODE_ENV=production
  
  # Activate corepack in the run container as well
  RUN corepack enable
  
  # Copy only the necessary files to run the app
  COPY --from=builder /app/package.json ./
  COPY --from=builder /app/pnpm-lock.yaml ./
  COPY --from=builder /app/.next ./.next
  COPY --from=builder /app/public ./public
  COPY --from=builder /app/node_modules ./node_modules
  COPY --from=builder /app/next.config.* ./

  COPY --from=builder /app/src ./src
  
  EXPOSE 3000
  
  # Start in production (must exist in your scripts)
  CMD ["pnpm", "start"]
  