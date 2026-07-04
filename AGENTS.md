# AGENTS.md — opencode session memory

opencode reads this file at the start of every session. It is the entry point so a fresh
session can pick up the curriculum without re-explanation.

## What this repo is

A personal K8s + MLOps learning journal. Stage-by-stage, tracked in `CURRICULUM.md`.
Runtime: kind single-node cluster on a CPU-only Mac. Focus area: pipelines & orchestration
(Kubeflow Pipelines first, Argo Workflows second).

## Read these first when resuming

1. `CURRICULUM.md` → "Current state" section at the top (the single source of truth).
2. `CURRICULUM.md` → "Session log" for recent history.
3. The active stage folder's `README.md`.
4. `NOTES.md` for gotchas.
5. `git log --oneline -15` for recent commits.

## Workflow per session

1. Read the files above.
2. Confirm with the user which stage to work on (default: the one in "Current state → Next up").
3. **Before writing manifests for a stage, fetch the relevant official docs live**
   (k8s.io, kubeflow.org, argo-workflows, mlflow.org, kserve.github.io, vllm).
   Do not rely on memorized API versions or install commands — they drift.
4. Fill in that stage's `concepts.md` (the "textbook chapter": definitions, mental
   models, why things exist, diagrams-in-text) AND `README.md` (the "lab guide":
   objectives, commands, expected output, "try next"). Write manifests under
   `manifests/`, code under `src/`. The user reads concepts.md first, then runs README.md.
5. Have the user run the commands; explain outputs; troubleshoot.
6. When the stage is done:
   - Tick its box in `CURRICULUM.md` → "Progress".
   - Update "Current state" (active stage, last completed, next up, last session date).
   - Append a one-line entry to "Session log".
   - Update `NOTES.md` with anything noteworthy.
   - Commit with message `<stage> — <short summary>`.

## Conventions

- One stage per folder. Treat completed stages as journal entries — don't edit them retroactively.
- No inline code comments (repo style). Explanations go in the stage's README.
- Manifests are uncommented YAML; explanations live in README.
- Commit once per stage; git history is part of the learning journal.
- `src/` holds minimal Python (FastAPI / sklearn / transformers) when the stage needs an app.

## Tooling (don't recompute — use these)

- Cluster: kind single-node. Context: `kind-kind`. Existing node: `kind-control-plane` (v1.36.1).
- Image loading: `kind load docker-image <name>:<tag>` (no registry).
- Ingress: **native via cloud-provider-kind v0.11.1** (host binary, runs with `sudo`
  in a dedicated terminal). NOT ingress-nginx. Start it each session:
  `sudo "$(go env GOPATH)/bin/cloud-provider-kind" --enable-default-ingress=true`
- LoadBalancer services: also native via cloud-provider-kind (external IP assigned automatically).
- MLflow: StatefulSet + 1Gi PVC + Service, port-forward for UI (or Ingress `mlflow.local`).
- KServe: too heavy for single-node CPU — use a lightweight FastAPI loader pattern instead;
  show KServe `InferenceService` manifests only as theory.
- LLM serving: `vllm --device cpu` with Qwen2.5-0.5B; fallback llama.cpp GGUF.
- Pipeline orchestrator: Kubeflow Pipelines (priority, stage 07), Argo Workflows (alt, stage 08).
- Cluster may need recreating with `00-bootstrap/manifests/kind-config.yaml` (8 GiB + port-mapped)
  before stage 07 (KFP) due to memory pressure.

## Useful commands

```bash
make help                  # list stage targets
kubectl config use-context kind-kind
kind load docker-image <img>:<tag>
kubectl port-forward svc/<name> <local>:<remote>
kubectl get pods -A -w
```

## Lint / typecheck

No code linting configured yet — Python in `src/` is minimal. If/when a stage adds a real
Python project with a linter, record the command here so it runs after each edit.