# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + built frontend ──────────────────────────────────
FROM python:3.12-slim
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Папка для загружаемых фото (на Render монтируется persistent disk)
RUN mkdir -p /data/uploads && ln -sf /data/uploads /app/backend/uploads

EXPOSE 8000
ENV DATABASE_URL=sqlite:////data/cars.db

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
