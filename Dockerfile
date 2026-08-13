FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

RUN groupadd --system icampus \
    && useradd --system --gid icampus --home-dir /app --shell /usr/sbin/nologin icampus \
    && mkdir -p /app/data /app/logs \
    && chown -R icampus:icampus /app

COPY --chown=icampus:icampus backend/ /app/

USER icampus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
