FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libcairo2 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m piper.download_voices --data-dir /opt/piper fr_FR-siwis-medium
ENV PIPER_VOICE_PATH=/opt/piper/fr_FR-siwis-medium.onnx
COPY app ./app
COPY tests ./tests
RUN python -m compileall -q app && python -m pytest -q tests/test_checkpoints.py tests/test_render_resume_integration.py tests/test_compression.py tests/test_narrative_policy.py tests/test_evidence_frames.py tests/test_motion_graphics.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
