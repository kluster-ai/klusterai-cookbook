#!/bin/bash

if [ -z "$KLUSTERAI_API_KEY" ] || [ -z "$GH_TOKEN" ] || [ -z "$SLACK_TOKEN" ]; then
    echo "Error: Required environment variables are not set"
    echo "Please set: KLUSTERAI_API_KEY, GH_TOKEN, and SLACK_TOKEN"
    exit 1
fi

mkdir -p /app/config
mkdir -p /app/logs

# Use template & envsubst to generate config.yaml
envsubst < /app/config.template.yaml > /app/config/config.yaml

if [ -n "$GITHUB_REPO" ]; then
    sed -i '/github:/a\    repo: "'"$GITHUB_REPO"'"' /app/config/config.yaml
fi


cat > /app/config/.env << EOL
KLUSTERAI_API_KEY=${KLUSTERAI_API_KEY}
GH_TOKEN=${GH_TOKEN}
SLACK_TOKEN=${SLACK_TOKEN}
EOL

# Set up cron job if CRON_SCHEDULE is provided
if [ ! -z "$CRON_SCHEDULE" ]; then
    touch /app/logs/app.log
    chmod 0644 /app/logs/app.log

    PYTHON_PATH=$(which python3)
    
    echo "$CRON_SCHEDULE $PYTHON_PATH /app/main.py --config /app/config/config.yaml --env /app/config/.env >> /app/logs/app.log 2>&1" > /etc/cron.d/github-report
    chmod 0644 /etc/cron.d/github-report
    crontab /etc/cron.d/github-report
    service cron start
fi

if [ "${RUN_NOW}" = "true" ]; then
    python3 main.py --config /app/config/config.yaml --env /app/config/.env >> /app/logs/app.log 2>&1
fi

# Keep container running if cron is enabled
if [ ! -z "$CRON_SCHEDULE" ]; then
    tail -f /app/logs/app.log
fi