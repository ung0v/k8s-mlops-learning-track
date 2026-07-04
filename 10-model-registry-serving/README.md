# 10 — Model registry & serving

> Status: scaffolded.

## Objectives
- Register a model in MLflow Model Registry, transition versions (None → Staging → Production).
- Load by alias / version from a FastAPI server (lightweight loader pattern).
- Show KServe `InferenceService` manifest as the production-grade alternative (theory; KServe pulls Knative+Istio, too heavy for our single-node CPU).
- Roll the server pod by promoting a new model version.

## Try next
`../11-feature-store-intro/`
