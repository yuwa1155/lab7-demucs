#!/bin/sh
set -eu
cd "$(dirname "$0")"

SOURCE_DIR="${MINIO_SOURCE_DIR:-../minio-source}"
SOURCE_COMMIT="$(cat minio/source-commit.txt)"
NODE="${KIND_NODE:-desktop-control-plane}"

if [ ! -d "$SOURCE_DIR/.git" ]; then
    git clone https://github.com/minio/minio.git "$SOURCE_DIR"
fi

ACTUAL_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
if [ "$ACTUAL_COMMIT" != "$SOURCE_COMMIT" ]; then
    echo "MinIO source commit differs."
    echo "Use a clean checkout at: $SOURCE_COMMIT"
    exit 1
fi

docker build -f minio/Dockerfile.source -t lab7-minio:v1 "$SOURCE_DIR"
docker build -t lab7-rest:v1 ./rest
docker build -t lab7-worker:v3 ./worker

for IMAGE in lab7-minio:v1 lab7-rest:v1 lab7-worker:v3; do
    ARCHIVE="$(mktemp /tmp/lab7-image-XXXXXX.tar)"
    docker save -o "$ARCHIVE" "$IMAGE"
    docker exec -i "$NODE" ctr -n k8s.io images import - < "$ARCHIVE"
    rm -f "$ARCHIVE"
done
