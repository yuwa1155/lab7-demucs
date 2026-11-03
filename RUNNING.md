# Lab 7 Implementation — Yuxiang Wang

## What I implemented

This service separates an uploaded MP3 into bass, drums, vocals, and other
tracks using the mdx_extra_q Demucs model.

The request flow is:

Client -> Traefik Ingress -> Flask REST -> MinIO + Redis -> Worker -> MinIO

MinIO stores the MP3 bytes. Redis stores JSON tasks containing the song hash,
model, and optional callback. The worker uses BLPOP to receive tasks and runs
Demucs as a subprocess. REST returns the resulting tracks as audio/mpeg.

## Tested environment

Windows with Ubuntu on WSL 2, Docker Desktop, and its single-node kind
Kubernetes cluster. The node container is named desktop-control-plane.
Docker Desktop's "Show system containers" option must be enabled.

This submission was tested locally. It has not been deployed to GKE.
Local access uses port forwarding to the Traefik controller.

## Build images

Start Docker Desktop and Kubernetes, then check:

    docker version
    kubectl get nodes

Run from the repository root:

    ./build-local.sh

This builds and imports lab7-minio:v1, lab7-rest:v1, and lab7-worker:v3
into the local Kubernetes node.

The MinIO source checkout defaults to ../minio-source. Its commit must match
minio/source-commit.txt. On a new machine, if the script reports a mismatch,
use a clean checkout and run:

    git -C ../minio-source checkout "$(cat minio/source-commit.txt)"

Then rerun ./build-local.sh.

MinIO is built from source because the original prebuilt image could not be
downloaded. minio/Dockerfile.source expects the MinIO source as its build
context, not this assignment repository.

## Install the Ingress controller

    helm repo add traefik https://traefik.github.io/charts
    helm repo update
    helm upgrade --install traefik traefik/traefik \
      --version 42.2.0 --namespace traefik --create-namespace
    kubectl rollout status deployment/traefik -n traefik --timeout=120s

## Deploy the application

    ./deploy-all.sh

The script deploys Redis and MinIO, creates the queue and output buckets,
and deploys REST, Worker, and the Ingress route.

The local MinIO credentials are rootuser / rootpass123.
These are demonstration credentials for this local lab.

MinIO uses a 5 GiB persistent volume claim. Redis is not persistent.
The worker model cache uses emptyDir: it survives container restarts within
the same Pod but is downloaded again when the Pod is replaced.

## Access and test

Keep this command running in a separate terminal:

    kubectl port-forward -n traefik service/traefik 8080:80

In another terminal:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install requests jsonpickle
    curl --fail http://localhost:8080/
    REST=localhost:8080 python short-sample-request.py
    kubectl logs -f deployment/worker

The first request downloads the model. Wait for Completed messages.
A queue can be empty while the worker is still processing a task.

Use the returned hash in these commands:

    curl --fail http://localhost:8080/apiv1/track/HASH/vocals.mp3 -o vocals.mp3
    curl -X DELETE http://localhost:8080/apiv1/remove/HASH/other.mp3
    curl -i http://localhost:8080/apiv1/track/HASH/other.mp3

The last request should return 404 after deletion.

## REST routes

- GET /: server health response.
- POST /apiv1/separate: JSON with Base64 mp3, optional model and callback.
  The supported/default model is mdx_extra_q. Returns hash and reason.
- GET /apiv1/queue: hashes of waiting tasks.
- GET /apiv1/track/<hash>/<track>: binary MP3 download.
- GET or DELETE /apiv1/remove/<hash>/<track>: remove an output track.

Valid tracks are bass.mp3, drums.mp3, vocals.mp3, and other.mp3.
base.mp3 is accepted as an alias for bass.mp3.

## Validation completed

- Both provided short MP3 samples were separated by the Kubernetes worker.
- Requests reached REST through Traefik and the Kubernetes Ingress.
- All four output tracks were uploaded for each sample.
- Download returned HTTP 200 with audio/mpeg and nonempty content.
- Deletion succeeded; a subsequent download returned HTTP 404.
- Queue queries worked and returned an empty queue after processing.
- deploy-all.sh was successfully run again on the existing deployment.

The provided callback uses localhost:5000, which points to the worker Pod
itself when called inside Kubernetes. That callback fails, but separation
still completes, as allowed by the assignment.

## Limitations

The service is a lab prototype. Failed tasks are marked failed in Redis
and are not automatically requeued. Duplicate submissions can run again.
It has no authentication and has only been tested with the short samples.
No public endpoint or GKE deployment was validated.

## Useful checks

    kubectl get pods
    kubectl get pods,pvc,svc -n minio-ns
    kubectl get ingress
    kubectl logs deployment/rest --tail=30
    kubectl logs deployment/worker --tail=30
