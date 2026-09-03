# Verified against livekit-agents==1.6.10's actual CLI (checked with
# `python agent.py --help` before writing this - `start` and
# `download-files` are confirmed real subcommands, not assumed).

FROM python:3.11-slim

WORKDIR /app

# ca-certificates: required for outbound TLS/WSS to LiveKit, Deepgram,
# Groq, and ElevenLabs. No other system packages are needed - the plugins
# used here (deepgram/openai/elevenlabs/silero/noise-cancellation) all ship
# prebuilt Python wheels (onnxruntime for the VAD model, no torch/ffmpeg
# required).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Prefetch model assets (the Silero VAD ONNX model, etc.) at build time so
# the container doesn't need internet access to fetch them on every cold
# start. Uses the module-level invocation (verified against the installed
# SDK: `python agent.py download-files` is deprecated as of 1.5.10 and
# additionally requires dummy LiveKit credentials just to import config.py -
# this form needs neither).
RUN python -m livekit.agents download-files

# Directory for the disposition JSONL log - mounted as a volume in
# docker-compose.yml so records survive container restarts.
RUN mkdir -p /app/data

CMD ["python", "agent.py", "start"]