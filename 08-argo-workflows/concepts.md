# 08 — Concepts: Argo Workflows

> Read this first. Then run the lab in `README.md`.
> Verified against argo-workflows.readthedocs.io — install via `quick-start-minimal.yaml`.
> This is the **follow-on** to KFP (stage 07) — Argo is the engine KFP is built on.

---

## 1. What is Argo Workflows?

**Argo Workflows** is a general-purpose workflow orchestrator for Kubernetes. You define a
**DAG** (or steps) of containers, and Argo runs them as Pods, handling:
- Dependencies between steps (A before B).
- Parallel execution (B and C at the same time after A).
- Artifact passing (A produces a file, B reads it).
- Retry on failure.
- Suspending/resuming.
- A UI showing the DAG and logs.

It's the **same engine KFP uses** — when you submit a KFP pipeline, KFP compiles it to an
Argo Workflow YAML, and the Argo workflow controller runs it. Stage 08 uses Argo directly,
so you see the raw engine without the KFP abstraction.

### Why use Argo directly instead of KFP?
- **Simplicity** — one YAML file, no Python SDK, no compilation step.
- **General purpose** — not ML-specific. Good for data pipelines, CI, batch jobs.
- **Lower overhead** — Argo's install is ~3 pods; KFP's is ~10+.
- **Direct control** — you see exactly what Pods get created, what args they get.

### Why KFP over Argo for ML?
- **Artifact tracking** — KFP's MinIO + ML Metadata integration is built-in. In Argo you
  configure artifact passing manually.
- **Python SDK** — KFP's `@dsl.component` is nicer than YAML for complex pipelines.
- **Caching** — KFP caches automatically; in Argo you configure it.
- **ML-specific UI** — KFP's UI shows artifacts, metrics, model lineage.

---

## 2. Argo Workflows architecture

```
   ┌─────────────────────────────────────────────┐
   │ argo namespace                              │
   │                                             │
   │  argo-server        ←── API + UI (port 2746)│
   │  workflow-controller ←── the reconcile loop │
   │  (optional: minio for artifacts)           │
   └─────────────────────────────────────────────┘
```

- **argo-server** — REST API + web UI. You submit workflows through it. Port 2746 (https).
- **workflow-controller** — watches for `Workflow` CRDs, creates Pods per step, tracks status.
- No MySQL, no MinIO by default (the `quick-start-minimal` install is truly minimal).

The key CRD is `Workflow` (`argoproj.io/v1alpha1`). A Workflow says: "run this DAG of containers."

---

## 3. The Workflow YAML

There are two ways to define a workflow:

### (a) Steps (sequential/parallel template references)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: iris-steps-
spec:
  entrypoint: main
  templates:
  - name: main
    steps:
    - - name: train
        template: train
    - - name: eval
        template: eval
        arguments:
          artifacts:
          - name: model
            from: "{{steps.train.outputs.artifacts.model}}"
  - name: train
    container:
      image: iris-train:0.1
      ...
  - name: eval
    container:
      image: iris-eval:0.1
      ...
```

`- -` (double dash) = parallel steps. `-` (single dash) = sequential. Each step references a
template (a container definition).

### (b) DAG (explicit dependencies)
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  generateName: iris-dag-
spec:
  entrypoint: main
  templates:
  - name: main
    dag:
      tasks:
      - name: train
        template: train
      - name: eval
        template: eval
        dependencies: [train]
        arguments:
          artifacts:
          - name: model
            from: "{{tasks.train.outputs.artifacts.model}}"
      - name: export
        template: export
        dependencies: [eval]
```

DAG is clearer for complex pipelines. We'll use DAG in the lab.

### Key fields
- `spec.entrypoint` — which template to start with.
- `spec.templates[]` — reusable container definitions.
- `templates[].dag.tasks[].dependencies` — list of tasks that must complete first.
- `templates[].dag.tasks[].template` — which template to run for this task.
- `templates[].dag.tasks[].arguments.artifacts` — inputs to the task (from another task's output).

---

## 4. Artifact passing in Argo

Argo has built-in **artifact support**. A template can declare:
- `outputs.artifacts` — files the container produces (Argo uploads them to an artifact store).
- `inputs.artifacts` — files the container needs (Argo downloads them from the store).

By default, the `quick-start-minimal` install uses an **emptyDir** for artifacts (ephemeral,
on the Pod's node). For production you'd configure S3/MinIO as the artifact store.

```yaml
- name: train
  container:
    image: iris-train:0.1
    outputs:
      artifacts:
      - name: model
        path: /tmp/model.joblib
```

Then in the eval task:
```yaml
- name: eval
  inputs:
    artifacts:
    - name: model
      path: /tmp/model.joblib
  container:
    image: iris-eval:0.1
```

Argo automatically:
1. After train's Pod completes, uploads `/tmp/model.joblib` to the artifact store.
2. Before eval's Pod starts, downloads the artifact to `/tmp/model.joblib`.

The `from: "{{tasks.train.outputs.artifacts.model}}"` in the task arguments connects them.

---

## 5. Installing Argo Workflows on kind

From the official quick start:

```bash
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml
```

> **Note:** Check https://github.com/argoproj/argo-workflows/releases for the latest version.
> The `quick-start-minimal` manifest includes the workflow controller + argo-server + minimal RBAC.

Wait for pods:

```bash
kubectl wait --for=condition=Ready pod -l app=argo-server -n argo --timeout=120s
kubectl wait --for=condition=Ready pod -l app=workflow-controller -n argo --timeout=120s
```

Access the UI:

```bash
kubectl -n argo port-forward service/argo-server 2746:2746
```

Open https://localhost:2746 (accept the self-signed cert).

---

## 6. KFP vs Argo — same engine, different abstraction

When you ran the KFP pipeline in stage 07, behind the scenes:
1. KFP compiled `pipeline.py` to IR YAML → then to an **Argo Workflow** YAML.
2. The Argo workflow-controller (installed by KFP) created Pods for each step.
3. Artifacts went to MinIO (configured by KFP).

In stage 08, you write the Workflow YAML directly. The difference:

| What            | KFP (stage 07)             | Argo (stage 08)               |
|-----------------|---------------------------|-------------------------------|
| Authoring       | Python `@dsl.pipeline`    | YAML `Workflow`               |
| Compilation     | `kfp compiler` → IR YAML   | none (YAML is the source)     |
| Artifact store  | MinIO (auto-configured)   | emptyDir or manual S3 config  |
| UI              | KFP dashboard              | Argo UI                       |
| Caching         | Automatic                 | Manual (cache config)         |
| Metadata        | ML Metadata (MySQL)        | None built-in                 |
| Controller pod  | KFP's workflow-controller  | Same workflow-controller      |

The workflow-controller is literally the same binary. KFP just wraps it with ML-specific
tooling (MinIO, ML Metadata, the Python SDK).

---

## 7. What you should be able to explain after stage 08

- What Argo Workflows is and how it differs from KFP.
- The two ways to define a workflow (steps vs DAG).
- How artifact passing works in Argo (outputs.artifacts → inputs.artifacts).
- Why KFP is "Argo + ML tooling" (same controller, more abstraction).
- When to use Argo directly vs KFP for a real ML pipeline.

---

## 8. Further reading

- Argo Workflows quick start: https://argo-workflows.readthedocs.io/en/stable/quick-start/
- Argo Workflows examples: https://github.com/argoproj/argo-workflows/tree/main/examples
- Argo Workflows CLI: https://argo-workflows.readthedocs.io/en/stable/walk-through/argo-cli/
- Argo Workflows DAG: https://argo-workflows.readthedocs.io/en/stable/walk-through/dag/
- Argo Workflows artifacts: https://argo-workflows.readthedocs.io/en/stable/walk-through/artifacts/
- Argo Workflows installation: https://argo-workflows.readthedocs.io/en/stable/installation/