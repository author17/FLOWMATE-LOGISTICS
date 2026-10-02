# Stage 1: build the React screens
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: API + built screens
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/dist frontend/dist
RUN mkdir -p /data/files
ENV STORAGE_DIR=/data/files
WORKDIR /app/backend
EXPOSE 8000
# AUTO_SEED=1 (practice copy only) re-creates the demo data every time the container starts
CMD ["sh", "-c", "if [ \"$AUTO_SEED\" = \"1\" ]; then python seed.py; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
