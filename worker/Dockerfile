FROM python:3.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_HOME=/models \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

RUN pip install torch==2.5.1+cpu torchaudio==2.5.1+cpu \
    --index-url https://pypi.org/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu

RUN pip install "numpy<2" demucs==4.0.1 diffq==0.2.4 redis minio requests

WORKDIR /app
COPY worker-server.py .
CMD ["python", "worker-server.py"]
