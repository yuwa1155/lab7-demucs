import base64
import binascii
import hashlib
import io
import json
import os
import re

import redis
from flask import Flask, jsonify, request, send_file
from minio import Minio
from minio.error import S3Error

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

db = redis.Redis(
    host=os.getenv("REDIS_HOST", "127.0.0.1"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)

storage = Minio(
    os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
    access_key=os.getenv("MINIO_ROOT_USER", "rootuser"),
    secret_key=os.getenv("MINIO_ROOT_PASSWORD", "rootpass123"),
    secure=False,
)

QUEUE = "toWorker"
TRACKS = {"bass.mp3", "vocals.mp3", "drums.mp3", "other.mp3"}


def object_name(songhash, track):
    if not re.fullmatch(r"[0-9a-f]{64}", songhash):
        return None
    # The REST README calls bass "base" in one place.
    if track == "base.mp3":
        track = "bass.mp3"
    if track not in TRACKS:
        return None
    return f"{songhash}-{track}"


@app.get("/")
def home():
    return "Music Separation Server", 200


@app.post("/apiv1/separate")
def separate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object"), 400

    encoded = data.get("mp3")
    if not isinstance(encoded, str) or not encoded:
        return jsonify(error="mp3 must be a Base64 string"), 400

    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return jsonify(error="Invalid Base64 mp3"), 400
    if not audio:
        return jsonify(error="Empty audio"), 400

    model = data.get("model", "mdx_extra_q")
    if model != "mdx_extra_q":
        return jsonify(error="Supported model: mdx_extra_q"), 400

    callback = data.get("callback")
    if callback is not None:
        if not isinstance(callback, dict):
            return jsonify(error="callback must be an object"), 400
        if not isinstance(callback.get("url"), str):
            return jsonify(error="callback.url must be a string"), 400

    songhash = hashlib.sha256(audio).hexdigest()
    storage.put_object(
        "queue",
        f"{songhash}.mp3",
        io.BytesIO(audio),
        len(audio),
        content_type="audio/mpeg",
    )

    job = {"hash": songhash, "model": model, "callback": callback}
    db.hset(f"job:{songhash}", mapping={"status": "queued"})
    db.rpush(QUEUE, json.dumps(job))
    return jsonify(hash=songhash, reason="Song enqueued for separation")


@app.get("/apiv1/queue")
@app.get("/apiv1/queue/")
def queue():
    jobs = [json.loads(item) for item in db.lrange(QUEUE, 0, -1)]
    return jsonify(queue=[job["hash"] for job in jobs])


@app.get("/apiv1/track/<songhash>/<track>")
def get_track(songhash, track):
    name = object_name(songhash, track)
    if name is None:
        return jsonify(error="Invalid song hash or track"), 400

    response = None
    try:
        response = storage.get_object("output", name)
        audio = response.read()
    except S3Error as error:
        if error.code in {"NoSuchKey", "NoSuchObject"}:
            return jsonify(error="Track not ready or not found"), 404
        raise
    finally:
        if response is not None:
            response.close()
            response.release_conn()

    return send_file(
        io.BytesIO(audio),
        mimetype="audio/mpeg",
        as_attachment=True,
        download_name=name,
    )


@app.route("/apiv1/remove/<songhash>/<track>", methods=["GET", "DELETE"])
def remove_track(songhash, track):
    name = object_name(songhash, track)
    if name is None:
        return jsonify(error="Invalid song hash or track"), 400
    storage.remove_object("output", name)
    return jsonify(hash=songhash, track=track, reason="Track removed")


if __name__ == "__main__":
    for bucket in ("queue", "output"):
        if not storage.bucket_exists(bucket):
            storage.make_bucket(bucket)
    app.run(host="0.0.0.0", port=5000)
