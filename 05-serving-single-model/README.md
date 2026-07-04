# 05 — Serving a single model

> Status: scaffolded.

## Objectives
- Serve a FastAPI app that loads the artifact from PVC.
- Expose via Service + Ingress (named host, e.g. `serve.local`).
- Add liveness + readiness probes.
- HorizontalPodAutoscaler scaling on CPU (metrics-server installed here).

## Try next
`../06-gitops-argocd/`
