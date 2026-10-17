FROM python:3.12-slim

# FFmpeg (Debian's build includes libass and libx264 for burned-in subtitles) and Noto fonts,
# so subtitles render in Indic, Arabic, Japanese and Korean scripts
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home app
WORKDIR /app

# CPU-only PyTorch: about 2 GB smaller than the default build with GPU libraries
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY main.py pipeline.py ./
# Created here so the named volumes mounted on them start out owned by the app user
RUN mkdir -p jobs /home/app/.cache && chown app:app jobs /home/app/.cache
USER app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
