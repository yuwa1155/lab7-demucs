#!/bin/sh
set -eu
cd "$(dirname "$0")"

./deploy-all.sh

kubectl port-forward service/redis 6379:6379 &
REDIS_PID=$!
kubectl port-forward -n minio-ns service/minio-proj 9000:9000 9001:9001 &
MINIO_PID=$!

trap 'kill "$REDIS_PID" "$MINIO_PID" 2>/dev/null || true' EXIT
trap 'exit 0' INT TERM
wait
