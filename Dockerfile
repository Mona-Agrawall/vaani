# Single-container image for Hugging Face Spaces: FastAPI serves both the API and the built
# frontend on port 7860. For running locally, docker-compose.yml (two containers) is simpler.

FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

# FFmpeg (Debian's build includes libass and libx264 for burned-in subtitles) and Noto fonts,
# so subtitles render in Indic, Arabic, Japanese and Korean scripts
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user ID 1000
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# CPU-only PyTorch: about 2 GB smaller than the default build with GPU libraries
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

RUN mkdir jobs && chown app:app jobs
USER app

# Spaces start with an empty disk after every restart, so bake the models into the image
# instead of downloading them on the first request
RUN python -c "import whisper; whisper.load_model('base')" \
    && python -c "from demucs.pretrained import get_model; get_model('htdemucs')"

COPY backend/main.py backend/pipeline.py ./
COPY --from=frontend /app/dist ./static
ENV FRONTEND_DIR=/app/static

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
