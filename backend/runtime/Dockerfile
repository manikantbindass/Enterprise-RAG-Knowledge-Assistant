FROM python:3.12-slim
WORKDIR /app
COPY backend/runtime/requirements.txt /tmp/requirements.txt
COPY backend/runtime/requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /app/data && chown app:app /app/data
COPY backend/runtime /app/backend/runtime
ENV RAG_DATA_DIR=/app/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "backend.runtime.main:app", "--host", "0.0.0.0", "--port", "8000"]
