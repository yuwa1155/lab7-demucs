import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import redis
import requests
from minio import Minio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

db = redis.Redis(
    host=os.getenv("REDIS_HOST", "127.0.0.1"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
    socket_connect_timeout=10,
    socket_timeout=30,
)
storage = Minio(
    os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
    access_key=os.getenv("MINIO_ROOT_USER", "rootuser"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD", "rootpass123"),
    secure=False,
)


def log(message):
    logging.info(message)
    try:
        db.lpush("logging", message)
        db.ltrim("logging", 0, 999)
    except redis.RedisError:
        logging.exception("Could not send log to Redis")


def process(job):
    songhash = job["hash"]
    model = job["model"]
    if model != "mdx_extra_q":
        raise ValueError("Unsupported model")

    db.hset(f"job:{songhash}", mapping={"status": "processing"})
    log(f"Starting separation: {songhash}")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / f"{songhash}.mp3"
        output = root / "output"
        storage.fget_object("queue", source.name, str(source))

        subprocess.run(
            [
                sys.executable, "-m", "demucs.separate",
                "-n", model,
                "--device", "cpu",
                "--mp3",
                "--shifts", "1",
                "--out", str(output),
                str(source),
            ],
            check=True,
        )

        tracks = output / model / songhash
        for part in ("bass", "drums", "vocals", "other"):
            filename = tracks / f"{part}.mp3"
            if not filename.is_file() or filename.stat().st_size == 0:
                raise RuntimeError(f"Missing output: {part}")
            storage.fput_object(
                "output",
                f"{songhash}-{part}.mp3",
                str(filename),
                content_type="audio/mpeg",
            )
            log(f"Uploaded {songhash}-{part}.mp3")

    db.hset(f"job:{songhash}", mapping={"status": "completed"})
    log(f"Completed: {songhash}")

    callback = job.get("callback")
    if callback:
        try:
            response = requests.post(
                callback["url"],
                json=callback.get("data"),
                timeout=10,
            )
            log(f"Callback response: {response.status_code}")
        except requests.RequestException as error:
            log(f"Callback failed: {error}")


def main():
    log("Worker started; waiting for tasks")
    while True:
        try:
            item = db.blpop("toWorker", timeout=5)
        except redis.RedisError:
            logging.exception("Redis connection failed; retrying")
            time.sleep(5)
            continue

        if item is None:
            continue

        job = None
        try:
            job = json.loads(item[1])
            process(job)
        except Exception as error:
            logging.exception("Task failed")
            if isinstance(job, dict) and isinstance(job.get("hash"), str):
                db.hset(
                    f"job:{job['hash']}",
                    mapping={"status": "failed", "error": str(error)},
                )
            log(f"Task failed: {error}")


if __name__ == "__main__":
    main()
