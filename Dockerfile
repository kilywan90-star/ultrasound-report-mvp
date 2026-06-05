# ── 超声报告语音 API — Docker 镜像 ──
FROM python:3.12-slim AS base

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# ── API 服务 (port 8800) ──
FROM base AS api
COPY . /app
WORKDIR /app
EXPOSE 8800
CMD ["python", "-m", "uvicorn", "microservice.main:app", "--host", "0.0.0.0", "--port", "8800"]

# ── Web 管理后台 (port 9999) ──
FROM base AS web
COPY . /app
WORKDIR /app/backend
EXPOSE 9999
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9999"]
