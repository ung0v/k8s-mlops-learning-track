# 07 — Lab: Kubeflow Pipelines (KFP v2)

> Read `concepts.md` first. This is the **primary pipeline stage** (your focus area).
> KFP standalone install takes ~3 minutes and needs ~4 GiB RAM.

---

## Objectives

1. Install KFP v2 standalone on kind.
2. Access the KFP UI.
3. Author a 3-step pipeline (train → evaluate → export) with the KFP SDK v2.
4. Compile the pipeline to IR YAML.
5. Submit a run via the SDK.
6. View the run in the KFP UI — see the DAG, step status, artifacts, metrics.
7. (Optional) Submit a run via the UI.
8. Clean up.

---

## 0. Prerequisites

- kind cluster running with at least 4 GiB RAM allocated to Docker.
- Python 3.10+ on your Mac.
- `cloud-provider-kind` running (not needed for KFP but good to have).

> **Memory check:** KFP pulls several large images (MySQL, MinIO, Argo, KFP API/UI).
> If your kind node is OOM-killed, increase Docker Desktop's memory to 8 GiB and recreate
> the cluster with `00-bootstrap/manifests/kind-config.yaml`.

---

## 1. Install KFP standalone

From the official docs (KFP v2, version `2.16.1`):

```bash
export PIPELINE_VERSION=2.16.1

kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
kubectl wait --for condition=established --timeout=60s crd/applications.app.k8s.io
kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$PIPELINE_VERSION"
```

Wait for all KFP pods to be Ready (~3 minutes):

```bash
kubectl get pods -n kubeflow -w
```

Expected (eventually all `Running`):

```
NAME                                 READY   STATUS    RESTARTS   AGE
ml-pipeline-xxxx                     1/1     Running   0          3m
ml-pipeline-ui-xxxx                  1/1     Running   0          3m
ml-pipeline-persistenceagent-xxxx    1/1     Running   0          3m
minio-xxxx                           1/1     Running   0          3m
mysql-xxxx                           1/1     Running   0          3m
workflow-controller-xxxx             1/1     Running   0          3m
```

Press `Ctrl+C` once all are Running.

> **If pods are stuck `Pending` or OOM-killed:** your kind node doesn't have enough memory.
> Increase Docker Desktop memory to 8 GiB, then `kind delete cluster && kind create cluster
> --config 00-bootstrap/manifests/kind-config.yaml` and re-install KFP.

---

## 2. Access the KFP UI

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80
```

Open http://localhost:8080 in your browser. You should see the KFP dashboard with:
- "Pipelines" tab (empty — we haven't uploaded any yet).
- "Runs" tab (empty).
- "Experiments" tab (empty).

---

## 3. Install the KFP SDK and compile the pipeline

```bash
cd 07-kubeflow-pipelines
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

Compile the pipeline:

```bash
python src/pipeline.py
```

Expected:

```
Pipeline compiled to iris_pipeline.yaml
```

This generates `iris_pipeline.yaml` — the IR YAML (intermediate representation) that KFP
understands. Open it in a text editor to see the structure: it's a large YAML with a
`pipelineInfo`, `root` (the DAG), and `components` sections. This is what KFP compiles
into an Argo Workflow at run time.

---

## 4. Submit a run via the SDK

```bash
python -c "
from kfp.client import Client
client = Client(host='http://localhost:8080')
run = client.create_run_from_pipeline_package(
    pipeline_file='iris_pipeline.yaml',
    arguments={'n_estimators': 20, 'max_depth': 3},
)
print(f'Run created: {run.run_id}')
"
```

Expected:

```
Run created: <uuid>
```

### Watch the run

In the KFP UI (http://localhost:8080):
1. Go to "Runs" tab.
2. Click on the latest run ("iris-train-pipeline").
3. You'll see the DAG: `train_model → evaluate_model → export_model`.
4. Each step turns green as it completes. Click a step to see logs, inputs, outputs, artifacts.

Or via CLI:

```bash
kubectl get pods -n kubeflow -l pipelines.kubeflow.org/pipeline-name=iris-train-pipeline -w
```

You'll see Pods created in sequence (train first, then eval, then export). Each Pod name has
the step name + a hash.

### Check the run status via SDK

```bash
python -c "
from kfp.client import Client
client = Client(host='http://localhost:8080')
runs = client.list_runs().runs
for r in runs:
    print(f'{r.display_name}: {r.state}')
"
```

Expected (after a minute or two):

```
iris-train-pipeline: SUCCEEDED
```

---

## 5. View artifacts and metrics

In the KFP UI:
1. Click on the completed run.
2. Click on the `evaluate_model` step.
3. In the "Output artifacts" section, you'll see a `Metrics` artifact with `accuracy` and
   `n_features` logged.
4. Click on the `train_model` step → "Output artifacts" → a `Model` artifact (the .joblib file).
5. You can download the model from the UI (it's stored in MinIO).

This is the key power of KFP over raw k8s Jobs: **artifacts are tracked and visible**.

---

## 6. Submit a run via the UI (optional)

1. In the KFP UI, click "Pipelines" → "Upload pipeline" → upload `iris_pipeline.yaml`.
2. Click "Create run" → set `n_estimators` to 50 → "Start".
3. Watch the run in the UI.

---

## 7. Re-run with caching

Re-submit the same pipeline with the same parameters:

```bash
python -c "
from kfp.client import Client
client = Client(host='http://localhost:8080')
run = client.create_run_from_pipeline_package(
    pipeline_file='iris_pipeline.yaml',
    arguments={'n_estimators': 20, 'max_depth': 3},
)
print(f'Run created: {run.run_id}')
"
```

KFP should skip the `train_model` step (cached — same inputs) and only re-run if something
changed. Look at the UI: the `train_model` step should show "Cached" instead of re-executing.

Now change the parameter:

```bash
python -c "
from kfp.client import Client
client = Client(host='http://localhost:8080')
run = client.create_run_from_pipeline_package(
    pipeline_file='iris_pipeline.yaml',
    arguments={'n_estimators': 50, 'max_depth': 4},
)
print(f'Run created: {run.run_id}')
"
```

This time all steps re-run (inputs changed). Compare the accuracy in the metrics between
the two runs in the UI.

---

## 8. Clean up

KFP is heavy — if you need the resources back:

```bash
export PIPELINE_VERSION=2.16.1
kubectl delete -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=$PIPELINE_VERSION"
kubectl delete -k "github.com/kubeflow/pipelines/manifests/kustomize/cluster-scoped-resources?ref=$PIPELINE_VERSION"
```

If you want to keep KFP for stage 09 (MLflow + KFP integration), leave it running.

---

## 9. What "done" looks like

- KFP UI accessible at http://localhost:8080.
- A pipeline run completed `SUCCEEDED` with the 3-step DAG visible.
- Artifacts (Model, Metrics) visible in the UI per step.
- Caching works (re-running with same params skips unchanged steps).
- You can explain: pipeline, component, run, experiment, artifact, parameter, caching.
- You can explain that KFP compiles to Argo Workflows under the hood.

---

## Try next

`../08-argo-workflows/` — use Argo Workflows directly (the engine KFP is built on), author
a DAG in YAML, compare the ergonomics vs KFP.

---

## Troubleshooting

- **Pods stuck in `Pending`** — not enough resources. `kubectl describe pod <name>` shows
  scheduling failures. Increase Docker memory, recreate the cluster, re-install KFP.
- **`ml-pipeline-ui` shows "Error: Failed to connect"`** — the API server isn't Ready yet.
  Wait for all pods, then refresh.
- **Pipeline run stuck in `Running`** — check the step pod: `kubectl logs -n kubeflow <pod>`.
  The KFP component may be failing to install scikit-learn (network issue in the container).
- **`kfp` SDK version mismatch** — KFP v2 SDK (`kfp>=2.0`) is required for KFP v2 backend.
  `pip install kfp==2.11.0` (or latest 2.x).
- **MinIO errors** — check `kubectl logs -n kubeflow minio-xxxx`. If the PVC is full, delete
  old runs/artifacts from the UI.
- **`Compiler().compile()` fails** — make sure the function signatures use KFP's `Output[Model]`
  / `Input[Model]` types, not plain `str` for artifacts.