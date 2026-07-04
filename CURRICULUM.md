# Kubernetes + MLOps Curriculum

A hands-on, stage-by-stage learning journal for Kubernetes with an MLOps/LLM focus.
Progression is tracked by stage folders; each stage has its own `README.md` (notes + objectives)
plus `manifests/` and `src/` you run yourself.

**Runtime:** kind single-node cluster (CPU-only Mac). GPU topics covered in theory.
**Pipeline orchestrator priority:** Kubeflow Pipelines first (deeper), Argo Workflows as follow-on.

---

## Current state  <-- READ THIS FIRST when resuming a session

- **Active stage:** none yet (curriculum just scaffolded)
- **Last completed:** 00-existing-flask-baseline (snapshot only, not a teaching stage)
- **Next up:** 01-k8s-fundamentals — Pods, ReplicaSets, Deployments, Services, Labels (bootstrap done)
- **Blockers / open questions:** none
- **Last session:** 2026-07-04 — installed cloud-provider-kind v0.11.1, recreated kind cluster with native Ingress support, validated end-to-end with kind's ingress example. Updated 00-bootstrap README to reflect the new architecture (no ingress-nginx needed).

> When you finish a session, update this section + append to "Session log" below.

---

## Session log

Append-only. One short entry per session: date, what you did, what's next.

- **2026-07-04 (session 2)** — Executed stage 00-bootstrap. Fetched live kind docs: discovered kind v0.32 supports Ingress natively via cloud-provider-kind (host binary, not a pod). Installed v0.11.1 via `go install`. Recreated cluster. Updated README + removed obsolete ingress-nginx manifest. Next: stage 01.
- **2026-07-04 (session 1)** — Scaffolded curriculum structure (16 stage folders + index + bootstrap). No k8s work yet. Next: run `make 00-bootstrap`.

---

## Progress

- [x] **00-bootstrap** — Cluster setup, native Ingress via cloud-provider-kind (no ingress-nginx)
- [x] **00-existing-flask-baseline** — Pre-curriculum snapshot (flask change-maker app + nginx deployment)
- [ ] **01-k8s-fundamentals** — Pods, ReplicaSets, Deployments, Services, Labels, Selectors
- [ ] **02-storage-config** — PV/PVC, StatefulSets, ConfigMaps, Secrets, init containers
- [ ] **03-packaging-ml-apps** — Multi-stage Docker, slim ML images, `kind load docker-image`
- [ ] **04-batch-ml-jobs** — Job, CronJob, parallelism; run sklearn training as a Job, artifact to PVC
- [ ] **05-serving-single-model** — Deployment+Service+HPA, liveness/readiness, serve FastAPI sklearn model
- [ ] **06-gitops-argocd** — Argo CD intro, declarative deploy of the serving app, sync waves
- [ ] **07-kubeflow-pipelines** — KFP standalone on kind, SDK v2 pipeline, train→eval→export, UI
- [ ] **08-argo-workflows** — Argo Workflows (lighter alternative), DAG/step templates, artifact passing
- [ ] **09-mlflow-tracking** — MLflow server on k8s (StatefulSet+PVC+Service), log from Jobs, port-forward UI
- [ ] **10-model-registry-serving** — MLflow Model Registry, promote versions, load by alias from FastAPI/KServe
- [ ] **11-feature-store-intro** — Feast minimal on kind (theory-heavy)
- [ ] **12-llm-inference-cpu** — Serve Qwen2.5-0.5B via vLLM/llama.cpp on CPU, HPA, latency probe
- [ ] **13-llm-finetune-pipeline** — Argo/KFP workflow: dataset→LoRA PEFT→MLflow registry→redeploy inference
- [ ] **14-monitoring-observability** — kube-prometheus-stack, custom inference metric, Evidently drift demo
- [ ] **15-capstone** — End-to-end: Argo CD deploys MLflow + serving + KFP nightly retrain; git-push triggers

---

## Pipelines & orchestration track (priority area)

| Topic                       | Stage | Outcome                                                                  |
|-----------------------------|-------|--------------------------------------------------------------------------|
| Job / CronJob               | 04    | One-shot and nightly training                                            |
| Kubeflow Pipelines          | 07    | SDK v2 pipeline, UI, artifacts, components                               |
| Argo Workflows              | 08    | DAG pipeline, comparison with KFP                                       |
| MLflow tracking             | 09    | Job logs run metrics/params to MLflow on k8s                             |
| Model Registry              | 10    | Promote version, fetch by stage alias                                    |
| GitOps (Argo CD)            | 06,15 | App+infra as code, sync waves, auto-redeploy on registry update           |
| Event-driven retraining     | 15    | CronJob → KFP run → registry bump → Argo CD notices → KServe pod rolls  |
| LLM fine-tune pipeline      | 13    | LoRA PEFT (CPU) pipelined with registry + serving                        |
| Monitoring the pipeline     | 14    | Workflow metrics, MLflow dashboards, drift signal feeds retrain trigger |

---

## Conventions

- One stage per folder; never edit a completed stage (treat as journal entry).
- Each stage has TWO docs:
  - **`concepts.md`** — the "textbook chapter": definitions, mental models, why things exist,
    diagrams-in-text, related official docs. Read this first.
  - **`README.md`** — the "lab guide": objectives, commands, expected output, "try next". Run this after.
- Manifests under `manifests/` are uncommented (per repo code style); explanations live in concepts.md.
- `src/` holds minimal Python (FastAPI / sklearn / transformers) when the stage needs an app.
- Commit once per stage; the git history doubles as a learning journal.

## Tooling

- Cluster: kind single-node (current `kind-control-plane`), v1.36.1
- Image loading: `kind load docker-image <name>` (no registry)
- Registry: local-only via kind; remote push not needed
- Ingress: **native**, via cloud-provider-kind v0.11.1 (host binary, runs with sudo)
- LoadBalancer services: also native via cloud-provider-kind
- MLflow: StatefulSet + 1Gi PVC + Service, port-forward for UI or Ingress `mlflow.local`
- KServe: heavy on single-node CPU; use lightweight FastAPI loader in stages, KServe manifests as theory
- LLM serving: `vllm --device cpu` (Qwen2.5-0.5B) or `llama.cpp` GGUF as fallback
- Pipeline orchestrator: Kubeflow Pipelines (priority), Argo Workflows (alternative)

## Notes

See `NOTES.md` for running gotchas, command snippets, and per-stage observations.

## How to resume a session

1. Read **"Current state"** at the top of this file — that's the single source of truth for where we are.
2. Read the active stage's `README.md` for objectives and commands.
3. Skim `NOTES.md` for recent gotchas.
4. Check `git log --oneline -10` for what was committed last.
5. When ending a session, update "Current state" + "Session log" and commit.