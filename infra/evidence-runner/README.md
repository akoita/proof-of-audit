# Cloud Run Evidence Runner

This directory contains the infrastructure artifacts for the remote executable evidence runner used by the `gcp_cloud_run` backend.

## Runtime contract

The deployed service exposes:

- `POST /execute`

Request body:

- `command`
- `env`
- `timeout_seconds`
- `memory_limit_bytes`
- `working_directory`
- `archive_format = "zip"`
- `archive_base64`

Response body:

- `returncode`
- `stdout`
- `stderr`

## Deployment notes

- build and deploy with [cloudbuild.yaml](/home/koita/dev/hackatons/proof-of-audit/infra/evidence-runner/cloudbuild.yaml)
- the service is intended to run one request per instance with authenticated invocation
- the runner image contains `forge` plus a small Python HTTP wrapper
- the backend archives the validated evidence root locally and posts it to the service for one-shot execution
