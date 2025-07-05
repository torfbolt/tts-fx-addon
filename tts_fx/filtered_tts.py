from flask import Flask, request, jsonify
import asyncio
from wyoming.client import AsyncClient
from wyoming.tts import Synthesize, SynthesizeVoice
from wyoming.audio import AudioChunk
import uuid
from pathlib import Path
import subprocess
import os

app = Flask(__name__)

piper_host = os.getenv("PIPER_HOST", "core-piper")
piper_port = os.getenv("PIPER_PORT", "10200")
VOICE = "en_US-danny-low"

OUT_TYPE = "mp3"
INPUT_DIR = Path("/media/tts_fx")
OUTPUT_DIR = INPUT_DIR
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def apply_apollo_effect(input_path: Path, output_path: Path):
    brown_noise_path = input_path.with_name("brownnoise.wav")
    stage1_path = OUTPUT_DIR / f"stage1_{input_path.name}"

    # Process TTS clip
    subprocess.run([
        "sox", "-t", "raw", "-r", "16000", "-e", "signed",
        "-b", "16", "-c", "1", str(input_path),
        "-r", "16000", "-t", "wav", str(stage1_path),
        "pitch", "-300", "highpass", "300", "lowpass", "3000",
        "compand", "0.3,1", "6:-70,-60,-20", "-5", "-90", "0.2",
        "reverb", "50", "50", "100", "100", "0", "2",
        "overdrive", "10", "gain", "-n", "-3"
    ], check=True)

    duration = subprocess.check_output(
        ["sox", "--i", "-D", str(stage1_path)], text=True).strip()

    # Generate brown noise
    subprocess.run([
        "sox", "-n", "-r", "16000", str(brown_noise_path),
        "synth", duration, "brownnoise", "vol", "0.08"
    ], check=True)

    # Use the processed stream + brown noise to mix
    subprocess.run([
        "sox", str(stage1_path), str(brown_noise_path), str(output_path),
        "bend", "0.3,5,0.3", "trim", "0", duration
    ], check=True)

    input_path.unlink(missing_ok=True)
    stage1_path.unlink(missing_ok=True)


async def synthesize(text: str, file_uuid: str) -> Path:
    input_wav = INPUT_DIR / f"{file_uuid}.wav"
    output_wav = OUTPUT_DIR / f"apollo_{file_uuid}.{OUT_TYPE}"

    # Connect to Piper (Wyoming)
    async with AsyncClient.from_uri(f'tcp://{piper_host}:{piper_port}'
                                    ) as client:
        synth = Synthesize(text=text, voice=SynthesizeVoice(name=VOICE),
                           ssml=True)
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
        apply_apollo_effect(input_wav, output_wav)
        return output_wav


@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "Missing 'message' in request"}), 400

    message = data["message"]
    file_uuid = data.get("uuid") or str(uuid.uuid4())

    try:
        output_path = asyncio.run(synthesize(message, file_uuid))
        return jsonify({"status": "ok", "output": str(output_path)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10300)
