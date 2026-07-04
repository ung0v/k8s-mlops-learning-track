# 07 — Kubeflow Pipelines (priority orchestrator)

> Status: scaffolded. This is the **primary** pipeline stage.

## Objectives
- Install KFP standalone on kind (MySQL + MinIO + API server + frontend + persistence agent).
- Bump kind node memory budget (see `manifests/kind-config-kfp.yaml`).
- Author a 3-step pipeline with the KFP SDK v2: train → evaluate → export artifact.
- Run the pipeline, view it in the KFP UI, inspect artifacts.
- Reuse a component across pipelines.

## Install (later)
```bash
# Recreate cluster with more memory if needed
kind delete cluster
kind create cluster --config manifests/kind-config-kfp.yaml

# Apply KFP manifests (subset for kind, see manifests/kfp/)
kubectl apply -k manifests/kfp/
```

## Author (later)
```bash
pip install kfp
python src/pipeline.py
# upload the generated pipeline.yaml to the KFP UI, or use the SDK client
```

## Notes
- KFP uses Argo Workflows under the hood; stage 08 is the lighter-weight Argo-only alternative for comparison.
- CPU-only: keep training steps tiny (sklearn on small datasets) so the pipeline finishes in seconds.

## Try next
`../08-argo-workflows/`
