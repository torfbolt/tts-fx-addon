from flask import Flask, request, jsonify
import asyncio
from wyoming.client import AsyncClient
from wyoming.tts import Synthesize, SynthesizeVoice
from wyoming.audio import AudioChunk
import uuid
from pathlib import Path
import subprocess
import os
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("filtered_tts")

app = Flask(__name__)

# Configurable environment
piper_host = os.getenv("PIPER_HOST", "core-piper")
piper_port = os.getenv("PIPER_PORT", "10200")
DEFAULT_VOICE = os.getenv("PIPER_VOICE", None)
OUT_TYPE = os.getenv("OUT_TYPE", "mp3")
TTS_FILTERS = os.getenv("TTS_FILTERS", "")
BACKGROUND_FILTERS = os.getenv("BACKGROUND_FILTERS", "")

# File paths
INPUT_DIR = Path("/media/tts_fx")
OUTPUT_DIR = INPUT_DIR
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def apply_sound_effect(input_path: Path, output_path: Path) -> str:
    background_path = input_path.with_name("background.wav")
    stage1_path = OUTPUT_DIR / f"stage1_{input_path.name}"

    logger.info("Applying SoX effect chain...")

    tts_cmd = [
        "sox", "-t", "raw", "-r", "16000", "-e", "signed",
        "-b", "16", "-c", "1", str(input_path),
        "-r", "16000", "-t", "wav", str(stage1_path)
    ] + TTS_FILTERS.split()

    logger.info(f"Running TTS filter command: {' '.join(tts_cmd)}")
    subprocess.run(tts_cmd, check=True)

    duration = subprocess.check_output(
        ["sox", "--i", "-D", str(stage1_path)], text=True).strip()
    logger.info(f"Audio duration: {duration} seconds")

    bg_cmd = [
        "sox", "-n", "-r", "16000", str(background_path),
        "synth", duration
    ] + BACKGROUND_FILTERS.split()

    logger.info(f"Running background filter command: {' '.join(bg_cmd)}")
    subprocess.run(bg_cmd, check=True)

    mix_cmd = [
        "sox", str(stage1_path), str(background_path), str(output_path),
        "bend", "0.3,5,0.3", "trim", "0", duration
    ]
    logger.info(f"Mixing audio: {' '.join(mix_cmd)}")
    subprocess.run(mix_cmd, check=True)

    # Cleanup
    input_path.unlink(missing_ok=True)
    stage1_path.unlink(missing_ok=True)
    background_path.unlink(missing_ok=True)

    return duration


async def synthesize(text: str, file_uuid: str, voice: str) -> (Path, str):
    input_wav = INPUT_DIR / f"{file_uuid}.wav"
    output_wav = OUTPUT_DIR / f"output_{file_uuid}.{OUT_TYPE}"

    logger.info(f"Synthesizing with voice: {voice or 'default'}")
    logger.info(f"Output format: {OUT_TYPE}")

    async with AsyncClient.from_uri(
            f'tcp://{piper_host}:{piper_port}') as client:
        synth = Synthesize(text=text) if voice is None else Synthesize(
            text=text, voice=SynthesizeVoice(name=voice))
        await client.write_event(synth.event())

        audio_data = bytearray()

        while True:
            event = await client.read_event()
            if event is None:
                raise Exception("No response from Piper server")
            elif event.type == "audio-chunk":
                chunk = AudioChunk.from_event(event)
                audio_data.extend(chunk.audio)
            elif event.type == "audio-stop":
                break

        input_wav.write_bytes(audio_data)
        duration = apply_sound_effect(input_wav, output_wav)
        return output_wav, duration


@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json()
    if not data or "message" not in data:
        logger.warning("Invalid request: missing 'message'")
        return jsonify({"error": "Missing 'message' in request"}), 400

    message = data["message"]
    file_uuid = data.get("uuid") or str(uuid.uuid4())
    voice = data.get("voice", DEFAULT_VOICE)

    logger.info(f"Received message: {message}")
    logger.info(f"UUID: {file_uuid}")

    try:
        output_path, duration = asyncio.run(synthesize(
            message, file_uuid, voice))
        logger.info(f"TTS generated: {output_path}")
        return jsonify({
            "status": "ok",
            "output": str(output_path),
            "duration": duration
        }), 200
    except Exception as e:
        logger.exception("TTS synthesis failed")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/health", methods=["GET"])
def health():
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10300)
