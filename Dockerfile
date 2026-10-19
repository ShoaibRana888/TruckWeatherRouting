# Stage 1: build the React app.
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Django serves the API and the built frontend (via WhiteNoise) from one service.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist
# Pre-compress the bundle; WhiteNoise serves the .gz files (the map chunk drops from ~1.8 MB to ~0.5 MB).
RUN python -m whitenoise.compress /app/frontend/dist
EXPOSE 8000
# One worker with threads: the forecast/directions caches are in-process, so all requests share them.
CMD ["sh", "-c", "gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 60"]
