FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      ffmpeg \
      git \
      libopus-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/lmdj
COPY . .

# The reference pipeline must keep numpy<2 with torch/demucs in its own venv.
RUN python -m venv references/demos/lmdj-song-pipeline/.venv \
    && references/demos/lmdj-song-pipeline/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && references/demos/lmdj-song-pipeline/.venv/bin/pip install --no-cache-dir \
       --index-url https://download.pytorch.org/whl/cpu \
       torch==2.11.0+cpu torchaudio==2.11.0+cpu \
    && references/demos/lmdj-song-pipeline/.venv/bin/pip install --no-cache-dir \
       -e references/demos/lmdj-song-pipeline

# LMDJ-owned packages run in a separate app venv.
RUN python -m venv /opt/app-venv \
    && /opt/app-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/app-venv/bin/pip install --no-cache-dir \
       -e packages/core-models \
       -e packages/patchify \
       -e workers/audio \
       -e apps/api

# Cache the fast Demucs model during image construction so the first job does
# not depend on a runtime download.
RUN references/demos/lmdj-song-pipeline/.venv/bin/python -c \
    "from demucs.pretrained import get_model; get_model('htdemucs')"

ENV LMDJ_JOBS_ROOT=/data/jobs
EXPOSE 8000

CMD ["/opt/app-venv/bin/uvicorn", "lmdj_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
