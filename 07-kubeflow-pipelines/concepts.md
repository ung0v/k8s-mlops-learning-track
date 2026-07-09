# 07 — Concepts: Kubeflow Pipelines (KFP v2)

> Read this first. Then run the lab in `README.md`.
> Verified against kubeflow.org/docs/components/pipelines — latest KFP version is `2.16.1`.
> This is the **primary pipeline orchestrator** stage (your focus area).

---

## 1. What is a pipeline, and why do we need an orchestrator?

In stages 04 and 05, we ran a single training script as a Job and served the model. Real ML
workflows are more complex:

```
   download data → preprocess → train → evaluate → validate → register → deploy
```

Each step is a container. Steps depend on each other (train needs the preprocessed data).
Some can run in parallel (hyperparameter sweep), some must be sequential. You need:

- **A DAG** (directed acyclic graph) of steps with dependencies.
- **Artifact passing** — step A's output (a file, a metric) becomes step B's input.
- **Caching** — if step A hasn't changed, don't re-run it.
- **Retry** — if a step fails, retry it without re-running the whole pipeline.
- **Visualization** — a UI showing the DAG, each step's status, logs, and artifacts.
- **Versioning** — each run is versioned, so you can compare runs and reproduce.

A **pipeline orchestrator** provides all of this. **Kubeflow Pipelines (KFP)** is the most
popular ML-focused orchestrator on k8s. **Argo Workflows** (stage 08) is the generic one KFP
is built on top of.

---

## 2. KFP v2 architecture (standalone on kind)

KFP standalone runs these components in the `kubeflow` namespace:

```
   ┌──────────────────────────────────────────────────────┐
   │ kubeflow namespace                                   │
   │                                                      │
   │  ml-pipeline (API server)  ←── UI talks to this     │
   │  ml-pipeline-ui             ←── the web dashboard   │
   │  ml-pipeline-persistence    ←── writes run metadata │
   │  minio                      ←── S3-compatible store │
   │  mysql                      ←── metadata database   │
   │  workflow-controller        ←── Argo Workflows (runs the actual pods) │
   │  argo-server                ←── Argo Workflows UI/API              │
   └──────────────────────────────────────────────────────┘
```

- **ml-pipeline** — the KFP API server. You submit pipelines to it via the SDK or UI.
- **ml-pipeline-ui** — the KFP dashboard. Shows pipelines, runs, experiments, artifacts.
- **minio** — an S3-compatible object store. Holds pipeline artifacts (model files, metrics, data).
- **mysql** — stores run metadata (experiment names, run status, parameters).
- **workflow-controller** — Argo Workflows under the hood. KFP compiles your pipeline to an
  Argo Workflow, and the workflow controller runs the actual Pods.
- **argo-server** — Argo Workflows API/UI. KFP uses it internally.

> **Key insight:** KFP v2 is an **abstraction layer on Argo Workflows**. You write pipelines
> in Python with the KFP SDK; KFP compiles them to Argo Workflow YAML; Argo runs them on k8s.
> This is why stage 08 (Argo Workflows) is the follow-on — it's the same engine, exposed directly.

---

## 3. The KFP SDK v2 — writing a pipeline

The KFP SDK (`kfp` Python package, v2) lets you define pipelines as Python functions decorated
with `@dsl.pipeline`. Each step is a **component** — a containerized function.

### A simple component

```python
from kfp import dsl

@dsl.component
def train_model(n_estimators: int) -> str:
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split

    X, y = load_iris(return_X_y=True)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    model = RandomForestClassifier(n_estimators=n_estimators)
    model.fit(X_train, y_train)

    joblib.dump(model, "/tmp/model.joblib")
    return "/tmp/model.joblib"
```

The `@dsl.component` decorator turns the function into a containerized component. KFP:
1. Inspects the function signature (parameters + return types).
2. Generates a container image (using the current Python environment or a specified base image).
3. Packages the function code into that container.
4. When the pipeline runs, KFP creates a Pod that runs the function.

### Composing components into a pipeline

```python
from kfp import dsl

@dsl.pipeline(name="iris-train-pipeline")
def iris_pipeline(n_estimators: int = 20):
    train_task = train_model(n_estimators=n_estimators)
    eval_task = evaluate_model(model_path=train_task.output)
    export_task = export_model(model_path=train_task.output, accuracy=eval_task.output)
```

- `train_task.output` — the return value of `train_model` (the model path). KFP passes this
  as an input to `evaluate_model`.
- The DAG is implicit from the data dependencies: `eval` depends on `train`, `export` depends
  on both. KFP figures out the order.

### Compiling the pipeline

```python
from kfp.compiler import Compiler
Compiler().compile(iris_pipeline, "iris_pipeline.yaml")
```

This generates an **IR YAML** (intermediate representation) — a single YAML file containing
the full pipeline definition. You submit this to KFP via the SDK or UI.

---

## 4. Pipeline concepts (memorize this table)

| Concept         | What it is                                                |
|-----------------|----------------------------------------------------------|
| **Pipeline**    | A reusable DAG template (Python function + IR YAML)     |
| **Component**   | A single step in the pipeline (containerized function)   |
| **Run**         | One execution of a pipeline with specific parameters      |
| **Experiment**  | A group of related runs (e.g. "iris-experiments")        |
| **Recurring Run** | A schedule that creates runs on a cron (like CronJob) |
| **Artifact**    | A file produced/consumed by a step (model, data, metrics)|
| **Parameter**   | A scalar value passed between steps (int, str, float)    |
| **Caching**     | If a step's inputs haven't changed, reuse the previous output |

### Artifacts vs parameters
- **Parameters** are small scalar values (strings, ints, floats). Passed as command-line args or env vars.
- **Artifacts** are files (model.joblib, metrics.json, a plot). Stored in MinIO, passed via URI.

```
   train step ──produces──> model artifact (URI in MinIO)
                ──passes──> URI to eval step
   eval step   ──reads──>   model artifact from MinIO
                ──produces──> metrics artifact
```

---

## 5. Installing KFP standalone on kind

From the official docs (verified July 2026):

```bash
export PIPELINE_VERSION=2.16.1

kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$PIPELINE_VERSION"
```

- `cluster-scoped-resources` — CRDs and cluster roles (applied first).
- `env/dev` — the development flavor (MySQL + MinIO + all KFP components). Uses default
  storage (PV/PVC for MinIO and MySQL). Not production-secure but perfect for learning.
- Takes ~3 minutes for all Pods to become Ready.

### Access the UI

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80
```

Open http://localhost:8080 — the KFP dashboard.

### Resource requirements
The `env/dev` flavor needs:
- ~4 GiB RAM for all KFP pods.
- ~2 CPU cores.
- ~10 GiB disk (for MinIO + MySQL + container images).

Your kind cluster with 8 GiB Docker allocation should handle it. If pods are OOM-killed,
increase Docker Desktop's memory allocation.

---

## 6. Running a pipeline

### Via the SDK

```python
from kfp.client import Client

client = Client(host="http://localhost:8080")
run = client.create_run_from_pipeline_package(
    pipeline_file="iris_pipeline.yaml",
    arguments={"n_estimators": 20},
)
```

### Via the UI

1. Open the KFP UI.
2. Click "Upload pipeline" → upload `iris_pipeline.yaml`.
3. Click "Create run" → set parameters → "Start".

### What happens when you submit a run

```
   SDK/UI ──submits IR YAML──> ml-pipeline API server
                                    │
                                    │ stores in MySQL
                                    │ compiles to Argo Workflow YAML
                                    ▼
                              Argo workflow-controller
                                    │
                                    │ creates Pods per step (in order, per DAG)
                                    ▼
                              Pods run train → eval → export
                                    │
                                    │ artifacts stored in MinIO
                                    │ metadata stored in MySQL
                                    ▼
                              KFP UI shows the DAG, status, artifacts
```

---

## 7. KFP vs Argo Workflows (stage 08 preview)

| Feature            | KFP v2                           | Argo Workflows               |
|--------------------|----------------------------------|------------------------------|
| Target audience    | ML engineers                     | DevOps / data engineers      |
| Pipeline authoring | Python SDK (`@dsl.pipeline`)     | YAML or Python SDK           |
| Artifact handling  | Built-in (MinIO + ML Metadata)  | Manual (artifact GC, S3)     |
| UI                 | Rich (DAG, artifacts, metrics)   | Basic (DAG, logs)            |
| Caching            | Automatic (per-step content hash)| Manual (config)               |
| Underlying engine  | Argo Workflows                   | Argo Workflows               |
| Best for           | ML experiments, model training  | Generic data pipelines, CI   |

KFP is the higher-level, ML-focused abstraction. Argo is the lower-level, general-purpose
engine. In stage 08 we'll use Argo directly for comparison.

---

## 8. What you should be able to explain after stage 07

- What a pipeline orchestrator does that a k8s Job doesn't.
- The KFP architecture (API server, UI, MinIO, MySQL, Argo controller).
- What `@dsl.component` and `@dsl.pipeline` do.
- The difference between artifacts (files) and parameters (scalars).
- How caching works (content hash of inputs → skip if unchanged).
- Why KFP compiles to Argo Workflow YAML (KFP is an abstraction on Argo).
- How to submit a pipeline via the SDK and via the UI.

---

## 9. Further reading

- KFP v2 installation: https://www.kubeflow.org/docs/components/pipelines/v2/installation/
- KFP v2 concepts: https://www.kubeflow.org/docs/components/pipelines/v2/concepts/pipeline/
- KFP v2 SDK: https://kubeflow-pipelines.readthedocs.io/en/stable/
- KFP v2 components: https://www.kubeflow.org/docs/components/pipelines/v2/user-guides/components/
- KFP v2 artifacts: https://www.kubeflow.org/docs/components/pipelines/v2/user-guides/data-handling/artifacts/
- KFP standalone deployment: https://www.kubeflow.org/docs/components/pipelines/v1/installation/standalone-deployment/
- KFP GitHub: https://github.com/kubeflow/pipelines