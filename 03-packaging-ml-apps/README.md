# 03 — Packaging ML apps for k8s

> Status: scaffolded.

## Objectives
- Build a multi-stage Docker image for a small ML app (sklearn).
- Minimize image size (slim base, no build deps in final stage).
- Load the image into kind without a registry (`kind load docker-image`).
- Set resource requests/limits and a non-root user.

## Try next
`../04-batch-ml-jobs/`
