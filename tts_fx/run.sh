#!/usr/bin/with-contenv bashio

# Required configuration
export PIPER_HOST=$(bashio::config 'piper_host')
export PIPER_PORT=$(bashio::config 'piper_port')

# Optional configuration with defaults
export PIPER_VOICE=$(bashio::config 'piper_voice')
export OUT_TYPE=$(bashio::config 'out_type')
export TTS_FILTERS=$(bashio::config 'tts_filters')
export BACKGROUND_FILTERS=$(bashio::config 'background_filters')

# Activate virtual environment
. /opt/venv/bin/activate

# Run the application
exec python3 /app/tts_fx.py
