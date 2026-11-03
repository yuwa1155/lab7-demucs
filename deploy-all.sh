#!/bin/sh
set -eu
cd "$(dirname "$0")"

kubectl apply -f redis/redis-deployment.yaml
kubectl apply -f redis/redis-service.yaml
kubectl create namespace minio-ns --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f minio/minio-local.yaml
kubectl apply -f minio/minio-external-service.yaml

kubectl rollout status deployment/redis --timeout=120s
kubectl rollout status deployment/minio-proj -n minio-ns --timeout=120s

# Create buckets before starting REST and Worker.
kubectl run bucket-init --rm -i --restart=Never \
  --image=lab7-worker:v3 --image-pull-policy=Never \
  --command -- python -c '
from minio import Minio
client = Minio(
    "minio-proj.minio-ns.svc.cluster.local:9000",
    access_key="rootuser",
    secret_key="rootpass123",
    secure=False,
)
for bucket in ("queue", "output"):
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    print("Bucket ready:", bucket)
'

kubectl apply -f rest/rest-deployment.yaml
kubectl apply -f rest/rest-service.yaml
kubectl apply -f worker/worker-deployment.yaml
kubectl apply -f rest/rest-ingress.yaml

kubectl rollout status deployment/rest --timeout=120s
kubectl rollout status deployment/worker --timeout=120s
