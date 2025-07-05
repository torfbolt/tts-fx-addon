#!/usr/bin/with-contenv bashio

export PIPER_HOST=$(bashio::config 'piper_host')
export PIPER_PORT=$(bashio::config 'piper_port')

# Activate virtual environment
. /opt/venv/bin/activate

exec python3 /app/filtered_tts.py
