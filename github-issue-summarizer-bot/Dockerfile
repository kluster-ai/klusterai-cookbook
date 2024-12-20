FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY config.template.yaml .

RUN mkdir -p batch_files
RUN mkdir -p config

COPY docker-run-entry.sh .
RUN chmod +x docker-run-entry.sh


ENTRYPOINT ["/app/docker-run-entry.sh"]