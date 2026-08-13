FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY static ./static

# 非 root 运行（容器逃逸提权防护）；uploads 目录需可写（本地存储兜底）
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads /app/uploads_private \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
