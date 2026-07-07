# 04 — Lab: Batch ML jobs

> Read `concepts.md` first. Build the images from stage 03 first (`make` or follow `../03-packaging-ml-apps/README.md`).

---

## Objectives

1. Create a PVC to hold the model artifact.
2. Run a one-shot training Job that writes the model to the PVC.
3. Verify the Job completed and the model file exists.
4. Schedule a CronJob that retrains every 2 minutes (for the lab; production would be daily).
5. Watch the CronJob create Jobs on schedule.
6. Clean up.

---

## 0. Prerequisites

- Images built and loaded: `iris-train:0.1` (see stage 03).
- kind cluster running.
- `kubectl get sc` shows `standard (default)`.

---

## 1. Create the PVC

```bash
kubectl apply -f manifests/pvc.yaml
kubectl get pvc model-pvc
```

Expected (Pending for a few seconds, then Bound — `WaitForFirstConsumer` means it binds when a Pod requests it):

```
NAME        STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
model-pvc   Pending                                       standard       2s
```

The PVC will stay Pending until the Job's Pod schedules and requests it. That's normal.

---

## 2. Run the training Job

```bash
kubectl apply -f manifests/job.yaml
kubectl get job iris-train
```

Expected:

```
NAME         COMPLETIONS   DURATION   AGE
iris-train   0/1           5s         5s
```

Watch the Pod:

```bash
kubectl get pods -l app=iris-train -w
```

Expected progression:

```
NAME              READY   STATUS              RESTARTS   AGE
iris-train-xxxx   0/1     Pending             0          0s
iris-train-xxxx   0/1     ContainerCreating   0          2s
iris-train-xxxx   0/1     Running             0          4s
iris-train-xxxx   0/1     Completed           0          15s
```

The `Completed` status is what makes a Job different from a Deployment — the Pod finished
and was **not** restarted. Press `Ctrl+C`.

Check the Job status:

```bash
kubectl get job iris-train
```

Expected:

```
NAME         COMPLETIONS   DURATION   AGE
iris-train   1/1           12s        30s
```

`COMPLETIONS: 1/1` means the Job is done. `DURATION` tells you how long training took.

### See the training logs

```bash
kubectl logs -l app=iris-train
```

Expected:

```
Loading iris dataset (n_estimators=20, max_depth=3)
Test accuracy: 0.9667
Model saved to /data/model.joblib
Metrics saved to /data/metrics.json
```

### Verify the model is on the PVC

Spin up a temporary Pod that mounts the same PVC:

```bash
kubectl run debug --rm -it --image=alpine:3.21 --restart=Never --overrides='
{
  "spec": {
    "containers": [{
      "name": "debug",
      "image": "alpine:3.21",
      "command": ["sh"],
      "stdin": true,
      "tty": true,
      "volumeMounts": [{"name": "data", "mountPath": "/data"}]
    }],
    "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "model-pvc"}}]
  }
}' -- sh -c 'ls -la /data && cat /data/metrics.json'
```

Expected:

```
total 8
drwxrwxrwx 1 root root 80 Jul  7 16:00 .
drwxr-xr-x 1 root root 80 Jul  7 16:00 ..
-rw-r--r-- 1 root root 45 Jul  7 16:00 metrics.json
-rw-r--r-- 1 root root 12345 Jul  7 16:00 model.joblib
{"accuracy": 0.9667, "n_estimators": 20, "max_depth": 3, "n_train": 120, "n_test": 30}
```

The model is on the PVC. **Leave the PVC in place** — stage 05's serving Pod will mount it.

---

## 3. Schedule a CronJob

```bash
kubectl apply -f manifests/cronjob.yaml
kubectl get cronjob iris-retrain
```

Expected:

```
NAME           SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
iris-retrain   */2 * * * *   False     0        <none>          5s
```

The schedule is every 2 minutes (`*/2 * * * *`). Wait ~2 minutes for the first scheduled run:

```bash
kubectl get jobs -l app=iris-train -w
```

After ~2 minutes you should see a new Job appear with a name like `iris-retrain-<timestamp>`:

```
NAME                      COMPLETIONS   DURATION   AGE
iris-train                1/1           12s        5m
iris-retrain-1719000000   0/1           0s         0s
iris-retrain-1719000000   1/1           12s        15s
```

Press `Ctrl+C`. Check the CronJob's status:

```bash
kubectl get cronjob iris-retrain
```

`LAST SCHEDULE` should now show a timestamp, and `ACTIVE` may briefly show 1 during the run.

### See the CronJob's Jobs

```bash
kubectl get jobs -l app=iris-train
```

You'll see the original `iris-train` Job plus any scheduled `iris-retrain-*` Jobs.

### Override params on the next run (optional)

The CronJob uses `N_ESTIMATORS=30, MAX_DEPTH=4` (slightly more capacity than the one-shot Job).
Check the logs of the most recent scheduled Job:

```bash
kubectl logs -l job-name=iris-retrain-<latest-timestamp>
```

(Substitute the actual Job name from `kubectl get jobs`.)

Expected:

```
Loading iris dataset (n_estimators=30, max_depth=4)
Test accuracy: 0.9667
Model saved to /data/model.joblib
Metrics saved to /data/metrics.json
```

The CronJob overwrote `model.joblib` on the PVC with the new model. (In production you'd
version the filename or use MLflow — we do that in stage 09.)

---

## 4. Clean up

```bash
kubectl delete -f manifests/cronjob.yaml
kubectl delete -f manifests/job.yaml
```

**Do NOT delete the PVC** — stage 05's serving Pod needs it:

```bash
kubectl get pvc model-pvc
```

It should still be Bound.

---

## 5. What "done" looks like

- `kubectl get job iris-train` shows `COMPLETIONS 1/1`.
- The Pod reached `Completed` status (not `Running` — that's the Job difference).
- The model file exists on the PVC (`kubectl run debug ... ls /data`).
- The CronJob created a new Job on schedule (~2 minutes).
- You can explain why a Job (not a Deployment) is the right tool for training.

---

## Try next

`../05-serving-single-model/` — mount the PVC the Job wrote to, serve the model with FastAPI,
expose via Ingress, add HPA + probes.

---

## Troubleshooting

- **Job `COMPLETIONS 0/1` and Pod `Running` forever** — the training script didn't exit. Check
  `kubectl logs -l app=iris-train`. Our script calls `sys.exit(0)` implicitly at the end of
  `train()`, so this shouldn't happen — but if you customize the script, make sure it exits.
- **Pod `ImagePullBackOff`** — you forgot to `kind load docker-image iris-train:0.1` (stage 03).
- **PVC stuck `Pending`** — `WaitForFirstConsumer` delays binding until a Pod schedules. If the
  Pod is also stuck Pending, check `kubectl describe pod <name>` for scheduling failures.
- **CronJob doesn't create Jobs** — check `kubectl describe cronjob iris-retrain` events. The
  schedule syntax may be wrong. `*/2 * * * *` is correct for every 2 minutes.
- **CronJob Jobs overlap** — set `concurrencyPolicy: Forbid` (already in our manifest).