# ---- stage 1: build the React frontend --------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Python API serving the compiled UI -----------------------
FROM python:3.12-slim
# libgomp is required by xgboost at runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend /build/dist /app/frontend_dist
ENV CHARGELENS_FRONTEND_DIST=/app/frontend_dist \
    PYTHONUNBUFFERED=1

# demo data seeds automatically on first boot (CHARGELENS_AUTO_SEED=true
# by default); mount a volume at /app/backend if you want it to persist
EXPOSE 8000
WORKDIR /app/backend
# shell form so $PORT (injected by Render/Railway/Fly/Cloud Run) is honored,
# falling back to 8000 for a plain `docker run -p 8000:8000`
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
