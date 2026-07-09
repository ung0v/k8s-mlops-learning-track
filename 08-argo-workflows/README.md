# 08 — Lab: Argo Workflows

> Read `concepts.md` first. Argo Workflows is the engine KFP is built on — stage 07 used it
> indirectly; here you use it directly.

---

## Objectives

1. Install Argo Workflows (minimal) on kind.
2. Access the Argo UI.
3. Submit a 3-task DAG workflow (train → eval → export).
4. Watch the DAG execute step by step.
5. View step logs and artifacts in the UI.
6. Compare the Argo experience vs KFP (stage 07).
7. Clean up.

---

## 0. Prerequisites

- kind cluster running.
- `iris-train:0.1` image built and loaded (stage 03).
- If KFP (stage 07) is still installed, that's fine — Argo Workflows uses its own namespace
  (`argo`) so they don't conflict. (KFP's workflow-controller runs in `kubeflow`; this
  installs a separate one in `argo`.)

---

## 1. Install Argo Workflows

Check the latest version at https://github.com/argoproj/argo-workflows/releases. As of July
2026, the latest stable is v3.6.x.

```bash
kubectl create namespace argo
kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml
kubectl wait --for=condition=Ready pod -l app=argo-server -n argo --timeout=120s
kubectl wait --for=condition=Ready pod -l app=workflow-controller -n argo --timeout=120s
```

Verify:

```bash
kubectl get pods -n argo
```

Expected:

```
NAME                                  READY   STATUS    RESTARTS   AGE
argo-server-xxxx                      1/1     Running   0          30s
workflow-controller-xxxx              1/1     Running   0          30s
```

Only 2 pods — much lighter than KFP's ~10+.

---

## 2. Install the Argo CLI

```bash
brew install argo
```

Or download directly:

```bash
curl -sL -o /usr/local/bin/argo "https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/argo-darwin-arm64"
chmod +x /usr/local/bin/argo
```

---

## 3. Access the Argo UI

```bash
kubectl -n argo port-forward service/argo-server 2746:2746
```

Open https://localhost:2746 in your browser (accept the self-signed cert). You'll see the
Argo Workflows dashboard with an empty workflow list.

---

## 4. Submit the workflow

### Via the CLI

```bash
argo submit -n argo --watch 08-argo-workflows/manifests/workflow.yaml
```

Expected (live DAG progression):

```
NAME                STATUS      AGE   DURATION   MESSAGE
iris-pipeline-xxxx  Running     5s    5s
iris-pipeline-xxxx  Succeeded   30s   28s
```

Press `q` to stop watching.

### Via the UI

1. In the Argo UI, click "+ Submit New Workflow".
2. Paste the contents of `manifests/workflow.yaml`.
3. Click "Create".

---

## 5. View the DAG and logs

### In the UI

1. Click on the completed workflow (`iris-pipeline-xxxx`).
2. You'll see the DAG: `train → eval → export`.
3. Click on `train` → "Logs" tab → see the training output.
4. Click on `eval` → "Logs" → see the accuracy.
5. Click on `export` → "Logs" → see the export message.
6. The "Artifacts" tab on each step shows the model file and metrics.

### Via the CLI

```bash
argo list -n argo
argo get -n argo @latest
argo logs -n argo @latest
```

The `@latest` is a shortcut for the most recent workflow.

---

## 6. Compare Argo vs KFP

After running both, compare:

| Aspect               | Argo (this stage)          | KFP (stage 07)               |
|----------------------|---------------------------|-------------------------------|
| Authoring            | YAML by hand              | Python `@dsl.component`      |
| Artifacts            | emptyDir (ephemeral)      | MinIO (persistent, trackable) |
| UI                   | Basic DAG + logs          | Rich: DAG + artifacts + metrics |
| Caching              | Not configured            | Automatic                     |
| Install weight       | 2 pods                    | ~10+ pods                     |
| Step status in UI    | ✅                         | ✅ + artifacts/metrics         |
| Retry                | Config per template       | Built-in                      |

**When to use which:**
- **Argo** for: generic data pipelines, CI/CD, batch jobs, when you don't need ML-specific
  artifact tracking.
- **KFP** for: ML experiments where you need artifact lineage, metrics comparison, and
  Python SDK ergonomics.

---

## 7. Re-run with a different parameter

The workflow accepts a `n_estimators` parameter. Override it:

```bash
argo submit -n argo --watch \
  --parameter n_estimators=50 \
  08-argo-workflows/manifests/workflow.yaml
```

Watch the new run execute. Compare the accuracy in the logs with the previous run.

---

## 8. Clean up

```bash
argo delete -n argo --all
kubectl delete -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml
kubectl delete namespace argo
```

If KFP (stage 07) is still installed, leave it — it has its own Argo in the `kubeflow` namespace.

---

## 9. What "done" looks like

- Argo UI accessible at https://localhost:2746.
- A workflow ran `SUCCEEDED` with the 3-task DAG visible.
- You can see step logs and artifacts in the UI.
- You can explain how Argo and KFP relate (KFP is Argo + ML tooling).
- You can articulate when to use Argo directly vs KFP.

---

## Try next

`../09-mlflow-tracking/` — install MLflow on k8s, log metrics/params/artifacts from Jobs and
KFP steps, view runs in the MLflow UI. This connects pipelines (07/08) to experiment tracking.

---

## Troubleshooting

- **`argo` CLI not found** — `brew install argo` or download the binary.
- **Workflow `Error` with `ImagePullBackOff`** — `iris-train:0.1` not loaded into kind.
  Re-run `kind load docker-image iris-train:0.1` (stage 03).
- **UI shows "Forbidden"** — the `quick-start-minimal` install allows anonymous access. If
  it's not working, check `kubectl get configmap workflow-controller-configmap -n argo`.
- **`eval` step fails with `ModuleNotFoundError: sklearn`** — the eval step uses `python:3.12-slim`
  which doesn't have sklearn. The workflow installs it inline via pip; if that fails, the
  container can't reach PyPI. Make sure your kind node has network access.
- **Artifacts not visible in UI** — the minimal install uses emptyDir for artifacts. They
  exist only while the Pod exists. If the Pod is already gone, artifacts are lost. For
  persistent artifacts, configure an S3/MinIO artifact store in the
  `workflow-controller-configmap`.