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
- `archive_base64` or `archive_gcs_uri`
- optional `archive_generation`

Response body:

- `returncode`
- `stdout`
- `stderr`

## Deployment notes

- build and deploy with [cloudbuild.yaml](/home/koita/dev/hackatons/proof-of-audit/infra/evidence-runner/cloudbuild.yaml)
- the service is intended to run one request per instance with authenticated invocation
- the runner image contains `forge`, `google-cloud-storage`, and a small Python HTTP wrapper
- the backend can either post the validated evidence root inline or stage it to GCS first and send a `gs://` reference
- if GCS staging is used, the runner service account needs object read access on the staging bucket
