# 09 — MLflow tracking on k8s

> Status: scaffolded.

## Objectives
- Run MLflow server as a StatefulSet with a 1Gi PVC for artifacts + SQLite/Postgres for metadata.
- Reach the UI via Ingress (`mlflow.local` — add to `/etc/hosts`).
- Log metrics/params/artifacts from a Job (stage 04) and from a KFP step (stage 07).
- Query runs via the MLflow client.

## Try next
`../10-model-registry-serving/`
