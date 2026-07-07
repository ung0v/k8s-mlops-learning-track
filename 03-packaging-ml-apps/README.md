# 03 — Lab: Packaging ML apps for k8s

> Read `concepts.md` first. This lab builds two images (training + serving) used by stages 04 and 05.

---

## Objectives

1. Build a single-stage ML image the naive way — see the bloat.
2. Build a multi-stage ML image — see the size savings.
3. Load both images into kind.
4. Verify the images are available to the cluster.

---

## 0. Prerequisites

- Docker running on your Mac.
- kind cluster running.
- Working directory: the repo root (`/Users/bovn/Desktop/Learning/k8s`).

---

## 1. Build the training image (multi-stage)

The training image lives in `04-batch-ml-jobs/` (it's used by stage 04's Job). Build it now:

```bash
cd 04-batch-ml-jobs
docker build -t iris-train:0.1 .
```

Expected (last lines):

```
 => exporting to docker image format                  3.5s
 => => exporting layers                              0.5s
 => => writing image sha256:...                      0.3s
 => => naming to docker.io/library/iris-train:0.1    0.0s
```

Check the size:

```bash
docker images iris-train:0.1
```

Expected (around 200-250 MB):

```
REPOSITORY   TAG   IMAGE ID       CREATED          SIZE
iris-train   0.1   <sha>          10 seconds ago   230MB
```

### Compare with a naive single-stage build

Build a naive version to see the difference. From the `04-batch-ml-jobs/` directory:

```bash
docker build -t iris-train-naive:0.1 -f - . <<'EOF'
FROM python:3.12-slim
WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/train.py .
ENTRYPOINT ["python", "train.py"]
EOF
```

Check the size:

```bash
docker images iris-train-naive:0.1
```

Expected (notice the size difference — the naive version keeps pip/setuptools/wheel in the image):

```
REPOSITORY          TAG   IMAGE ID       CREATED          SIZE
iris-train-naive    0.1   <sha>          5 seconds ago   350MB
```

The multi-stage image is ~120 MB smaller because it doesn't include pip, setuptools, wheel, or the build cache. Run `docker history iris-train:0.1` vs `docker history iris-train-naive:0.1` to see exactly which layers differ.

### Test the training image locally (no k8s)

```bash
docker run --rm -v /tmp/iris-data:/data -e N_ESTIMATORS=10 iris-train:0.1
```

Expected output:

```
Loading iris dataset (n_estimators=10, max_depth=3)
Test accuracy: 0.9667
Model saved to /data/model.joblib
Metrics saved to /data/metrics.json
```

Verify the artifacts were written:

```bash
ls -la /tmp/iris-data/
cat /tmp/iris-data/metrics.json
```

Clean up:

```bash
rm -rf /tmp/iris-data
docker rmi iris-train-naive:0.1
```

---

## 2. Build the serving image (multi-stage)

The serving image lives in `05-serving-single-model/`:

```bash
cd ../05-serving-single-model
docker build -t iris-serve:0.1 .
```

Check the size:

```bash
docker images iris-serve:0.1
```

Expected (around 250-300 MB — slightly bigger than training because it includes fastapi + uvicorn):

```
REPOSITORY   TAG   IMAGE ID       CREATED          SIZE
iris-serve   0.1   <sha>          10 seconds ago   280MB
```

### Test the serving image locally (no k8s)

First create a model file to mount:

```bash
docker run --rm -v /tmp/iris-data:/data -e N_ESTIMATORS=10 iris-train:0.1
```

Now run the server with the model mounted:

```bash
docker run --rm -p 8000:8000 -v /tmp/iris-data:/data:ro iris-serve:0.1
```

In another terminal, test the endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}'
```

Expected (last curl):

```json
{"class_label": 0, "class_name": "setosa"}
```

(5.1, 3.5, 1.4, 0.2 is a classic setosa sample.)

Stop the server (`Ctrl+C`), clean up:

```bash
rm -rf /tmp/iris-data
```

---

## 3. Load both images into kind

```bash
kind load docker-image iris-train:0.1
kind load docker-image iris-serve:0.1
```

Expected (each takes a few seconds):

```
Image: "iris-train:0.1" with ID <sha> found and loaded.
Image: "iris-serve:0.1" with ID <sha> found and loaded.
```

### Verify the images are in the cluster

```bash
docker exec kind-control-plane crictl images | grep iris
```

Expected:

```
docker.io/library/iris-serve:0.1   <sha>   280MB
docker.io/library/iris-train:0.1  <sha>   230MB
```

The images are now available to Pods in the kind cluster. When you create a Job (stage 04) or Deployment (stage 05) with `image: iris-train:0.1` and `imagePullPolicy: IfNotPresent`, kubelet will find the image in containerd without trying to pull from a registry.

---

## 4. What "done" looks like

- `docker images iris-train:0.1` shows ~230 MB (multi-stage).
- `docker images iris-serve:0.1` shows ~280 MB (multi-stage).
- `docker exec kind-control-plane crictl images | grep iris` shows both images.
- You can explain why the multi-stage image is smaller than the naive one.
- You can explain what `kind load docker-image` does and why `imagePullPolicy: IfNotPresent` is needed.

---

## Try next

`../04-batch-ml-jobs/` — run the training image as a Kubernetes Job, save the model to a PVC, schedule nightly retrains with CronJob.

---

## Troubleshooting

- **`docker build` fails on `COPY src/requirements.txt`** — you must be in the `04-batch-ml-jobs/` or `05-serving-single-model/` directory (the Dockerfile uses `COPY src/...` which is relative to the build context).
- **`kind load docker-image` is slow** — the image is large. Verify you built the multi-stage version, not the naive one.
- **`crictl images | grep iris` returns nothing** — the load failed. Check `kind load docker-image` output for errors. Make sure you tagged the image correctly (`-t iris-train:0.1`, not `:latest`).
- **`docker run` of serving image fails with "Model not found"** — you need to mount a volume with a trained model (`-v /tmp/iris-data:/data:ro`). Run the training image first to create the model.