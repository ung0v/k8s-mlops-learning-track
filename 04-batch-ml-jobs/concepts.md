# 04 — Concepts: Batch ML jobs (Job, CronJob)

> Read this first. Then run the lab in `README.md`.
> Verified against k8s v1.36 docs — `batch/v1` for both Job and CronJob.

---

## 1. Why Jobs exist (and when to use them vs Deployments)

A **Deployment** runs Pods that should **never stop** — a web server, an API, a worker that
polls a queue. If a Pod crashes, the ReplicaSet restarts it. If a Pod finishes its work and
exits 0, the ReplicaSet **restarts it anyway** (because `restartPolicy: Always` is the default
for Deployments). That's wrong for batch work.

A **Job** runs Pods that **should stop when the work is done**. When the Pod exits 0, the
Job considers it succeeded and does **not** restart it. When the Pod exits non-zero, the Job
retries (up to `backoffLimit`). When all requested completions are done, the Job is `Complete`.

| Workload     | Pod exits 0          | Pod exits non-0         | Use case              |
|--------------|----------------------|-------------------------|-----------------------|
| Deployment   | Restart Pod          | Restart Pod             | Web server, API      |
| Job          | Mark succeeded       | Retry up to backoffLimit| Training, batch, ETL  |
| CronJob      | (creates Jobs on schedule) | (Job retries)      | Nightly retrain       |

For MLOps, Jobs are the natural fit for:
- Training a model (run once, produce an artifact, exit).
- Batch inference (process a file, write predictions, exit).
- Data preprocessing (ETL before training).
- Hyperparameter sweeps (parallel Jobs with different params).

---

## 2. The Job resource

### The manifest, field by field

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: iris-train
spec:
  backoffLimit: 4
  activeDeadlineSeconds: 300
  completions: 1
  parallelism: 1
  template:
    metadata:
      labels:
        app: iris-train
    spec:
      restartPolicy: OnFailure
      containers:
      - name: train
        image: iris-train:0.1
        imagePullPolicy: IfNotPresent
        env:
        - name: N_ESTIMATORS
          value: "20"
        - name: MODEL_PATH
          value: /data/model.joblib
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: model-pvc
```

Key fields:
- `apiVersion: batch/v1` — the batch API (not `apps/v1` like Deployments).
- `spec.backoffLimit: 4` — retry up to 4 times on failure (default 6). After that, the Job is marked `Failed`.
- `spec.activeDeadlineSeconds: 300` — kill the Job if it runs longer than 5 minutes. Prevents runaway training.
- `spec.completions: 1` — how many successful Pod completions the Job needs. Default 1.
- `spec.parallelism: 1` — how many Pods to run in parallel. Default 1. Set >1 for parallel jobs.
- `spec.template` — the Pod template. Same structure as a Deployment's template.
- `spec.template.spec.restartPolicy: OnFailure` — restart the Pod **in-place** on failure (the same Pod object, containerd restarts the container). The alternative `Never` means the Job creates a **new** Pod on failure (useful when you want a clean slate each retry).

> **Critical:** `restartPolicy` for Jobs must be `OnFailure` or `Never`. It cannot be `Always` (that's for Deployments). If you set `Always`, the API server rejects the Job.

### Pod status for Jobs
- `STATUS: Completed` — the Pod exited 0. The Job is done.
- `STATUS: Error` — the Pod exited non-0 and `restartPolicy: Never` (a new Pod will be created up to `backoffLimit`).
- `STATUS: CrashLoopBackOff` — the Pod keeps crashing and `restartPolicy: OnFailure` is restarting it in-place. Eventually the Job gives up after `backoffLimit`.

### `kubectl get job`
```
NAME         COMPLETIONS   DURATION   AGE
iris-train   1/1           12s        30s
```
`COMPLETIONS: 1/1` means 1 of 1 requested completions succeeded. `DURATION` is how long the Job took.

---

## 3. Parallel Jobs (hyperparameter sweep)

For a sweep, you want N Pods running in parallel, each with different params. Two patterns:

### Pattern A: Multiple Jobs (one per param set)
Create N Job manifests (or one Job with `completions: N, parallelism: N` and indexed Pods).
Each Pod uses `JOB_COMPLETION_INDEX` env var (set automatically by k8s for indexed Jobs) to
pick its params from a ConfigMap.

### Pattern B: Indexed Job
```yaml
spec:
  completions: 5
  parallelism: 5
  completionMode: Indexed
```
Each Pod gets `JOB_COMPLETION_INDEX` (0-4). The Pod reads its params from a ConfigMap keyed
by index. This is the cleanest pattern for hyperparameter sweeps.

We won't build a full sweep in this lab (it's covered conceptually); the lab runs a single
training Job, then a CronJob that retrains nightly.

---

## 4. CronJob — scheduled Jobs

A **CronJob** creates Jobs on a schedule (cron format). Use cases:
- Nightly model retrain.
- Hourly data refresh.
- Daily batch inference.

### The manifest

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: iris-retrain
spec:
  schedule: "*/2 * * * *"
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: train
            image: iris-train:0.1
            imagePullPolicy: IfNotPresent
            env:
            - name: N_ESTIMATORS
              value: "30"
            volumeMounts:
            - name: data
              mountPath: /data
          volumes:
          - name: data
            persistentVolumeClaim:
              claimName: model-pvc
```

Key fields:
- `spec.schedule: "*/2 * * * *"` — cron format: minute hour day-of-month month day-of-week. This runs every 2 minutes (for the lab; production would be `0 2 * * *` for 2 AM daily).
- `spec.jobTemplate` — a Job spec nested inside the CronJob. Each scheduled run creates a new Job from this template.
- `spec.concurrencyPolicy` — `Allow` (default), `Forbid` (don't start a new Job if the previous one is still running), or `Replace` (cancel the running Job and start a new one). For training, use `Forbid` to prevent overlapping writes to the model.
- `spec.successfulJobsHistoryLimit` / `failedJobsHistoryLimit` — how many completed/failed Jobs to keep for inspection (default 3/1).

### Cron format cheat sheet
```
┌──────── minute (0-59)
│ ┌────── hour (0-23)
│ │ ┌──── day of month (1-31)
│ │ │ ┌── month (1-12)
│ │ │ │ ┌ day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```
- `0 2 * * *` — daily at 2 AM
- `*/2 * * * *` — every 2 minutes (lab)
- `0 0 1 * *` — first day of every month at midnight
- `0 */4 * * 1-5` — every 4 hours on weekdays

---

## 5. Sharing the model artifact via PVC

The training Job and the serving Deployment (stage 05) need to share the model file. Two
options:

### (a) PVC (what we'll use)
The Job writes `model.joblib` to a PVC. The serving Deployment mounts the **same** PVC (read-only)
and loads the model at startup. Simple, works on a single node. Caveat: if the Job and the
serving Pods are on different nodes, the PVC must be `ReadWriteMany` (NFS) or you need a
distributed filesystem. On single-node kind, `ReadWriteOnce` is fine.

### (b) Object storage (production pattern)
The Job uploads the model to S3/MinIO/artifact registry. The serving Pod downloads it on
startup (or an init container does). This is what MLflow + stages 09/10 will do later.

For this stage, we use a PVC — the simplest pattern that demonstrates the idea. Stage 09
replaces the PVC with MLflow's artifact store.

---

## 6. The mental model

```
   kubectl apply -f job.yaml
        │
        ▼
   Job controller (in controller-manager)
        │  creates a Pod from job.spec.template
        ▼
   Pod runs: python train.py
        │  writes /data/model.joblib (PVC)
        │  exits 0
        ▼
   Job controller sees exit 0
        │  marks Job COMPLETIONS 1/1
        │  does NOT restart the Pod (unlike a Deployment)
        ▼
   PVC now has the model
        │
        ▼
   (later, stage 05) Serving Deployment mounts the same PVC
       └─> loads model.joblib at startup
```

For a CronJob, the CronJob controller wakes on schedule, creates a new Job (which creates a
new Pod), and the cycle repeats.

---

## 7. What you should be able to explain after stage 04

- Why a Job (not a Deployment) is the right tool for training.
- What `backoffLimit`, `completions`, `parallelism` mean.
- Why `restartPolicy: OnFailure` (not `Always`) for Jobs.
- The cron format and how to schedule a daily 2 AM retrain.
- What `concurrencyPolicy: Forbid` does and why it matters for training.
- How the Job and the serving Pod share the model via a PVC.
- The full chain from `kubectl apply -f job.yaml` to "model file on PVC".

---

## 8. Further reading (official docs)

- Jobs: https://kubernetes.io/docs/concepts/workloads/controllers/job/
- CronJobs: https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
- Run a Job: https://kubernetes.io/docs/concepts/workloads/controllers/job/#running-an-example-job
- Indexed Job for parallel processing: https://kubernetes.io/docs/tasks/job/indexed-parallel-processing-static/
- Pod restartPolicy: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#restart-policy
- Cron format (Wikipedia): https://en.wikipedia.org/wiki/Cron