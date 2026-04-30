#!/bin/bash
set -e

# Ensure data directories exist (for first run with empty volume)
mkdir -p /app/data/logs /app/data/faiss /app/data/knowledge_bases

# Link .env into backend CWD so pydantic-settings can find it
if [ -f /app/.env ] && [ ! -f /app/backend/.env ]; then
    ln -s /app/.env /app/backend/.env
fi

echo "========================================="
echo " SuperDeepAnalyze - Starting"
echo "========================================="
echo "Data dir:  /app/data"
echo "Logs dir:  /app/data/logs"
echo "========================================="

# Start supervisor (manages nginx + uvicorn)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/superdeep.conf
