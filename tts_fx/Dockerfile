FROM ghcr.io/home-assistant/aarch64-base:latest

RUN apk add --no-cache python3 py3-pip sox sox-dev curl bash

# Create and activate venv, then install Python deps inside it
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install flask wyoming

WORKDIR /app
COPY run.sh .
COPY tts_fx.py .

RUN chmod +x run.sh

CMD ["/app/run.sh"]

