FROM node:22-bookworm-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV API_INTERNAL_URL=http://127.0.0.1:8000
RUN npm run build


FROM node:22-bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY engine/ ./engine/
COPY scripts/ ./scripts/
COPY --from=frontend-builder /build/frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /build/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /build/frontend/public ./frontend/public
COPY deploy/start-public-demo.sh ./deploy/start-public-demo.sh

ENV INVOICE_APP_ENV=demo \
    PUBLIC_DEMO_READ_ONLY=1 \
    API_INTERNAL_URL=http://127.0.0.1:8000 \
    PORT=10000 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/data/uploads \
    && /opt/venv/bin/python scripts/seed_demo.py

EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||10000)+'/api/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

CMD ["/bin/sh", "/app/deploy/start-public-demo.sh"]
