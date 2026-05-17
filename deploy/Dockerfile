FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY src ./src
COPY config ./config

ENV PYTHONPATH=/app/src \
    GRIMSPROUT_CONFIG=/app/config/config.yaml

CMD ["python", "-m", "grimsprout"]
