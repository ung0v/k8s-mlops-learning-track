# 03 — Concepts: Packaging ML apps for Kubernetes

> Read this first. Then run the lab in `README.md`.
> This stage has no manifests of its own — it teaches the image-build pattern that stages 04 and 05 use.

---

## 1. Why packaging matters for ML on k8s

Every Pod runs a container, and every container runs an image. On kind you can't `docker pull`
from a registry during the lab (we have no registry) — you build the image on your Mac, then
`kind load docker-image` to push it into the kind node's containerd. This means:

1. The image must be self-contained: app code + dependencies + Python runtime.
2. The image must be small enough to load quickly and not waste the kind node's disk.
3. The image must run as a non-root user (security best practice, required by many Pod Security Standards).
4. The image must accept configuration via env vars (so k8s ConfigMaps/Secrets can inject it).

This stage teaches the **multi-stage build** pattern — the standard way to achieve all four goals.

---

## 2. The single-stage problem

Look at the existing `00-existing-flask-baseline/Dockerfile`:

```dockerfile
FROM python:3.8.8-slim-buster
WORKDIR /app
COPY . app.py /app/
RUN pip install --no-cache-dir --upgrade pip &&\
    pip install --no-cache-dir -r requirements.txt
EXPOSE 8080
ENTRYPOINT [ "python" ]
CMD [ "app.py" ]
```

Problems:
- **Old base image** (`python:3.8.8-slim-buster` — 3.8 is EOL, buster is Debian 10, also EOL).
- **pip cache + build deps** stay in the final image (bloat).
- **Runs as root** (default for `python:3.x-slim`) — security risk.
- **`COPY . app.py /app/`** has a typo (copies `.` and `app.py` — the `.` wins, `app.py` is treated as a destination dir name). This is the original repo's bug.
- **No resource limits** baked in (k8s sets those, but the image should be lean).

A naive ML image based on `python:3.12` (not slim) + `pip install scikit-learn` would be ~1.5 GB. We can do better.

---

## 3. The multi-stage build pattern

A **multi-stage Dockerfile** has multiple `FROM` lines. Each `FROM` starts a new build stage.
Only the **final stage** becomes the image; earlier stages are discarded. You copy only what
you need from earlier stages using `COPY --from=<stage>`.

```
   Stage 1 (builder)              Stage 2 (final)
   ┌─────────────────────┐        ┌─────────────────────┐
   │ python:3.12-slim    │        │ python:3.12-slim    │
   │ + pip install ...   │  COPY  │ (no pip, no cache)  │
   │ + build tools       │ ─────> │ + only the installed│
   │ (gcc, wheels, etc.) │        │   packages + app.py │
   │ ~500 MB             │        │ ~150 MB             │
   └─────────────────────┘        └─────────────────────┘
```

### The training image Dockerfile (stage 04)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY src/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/train.py .
ENTRYPOINT ["python", "train.py"]
```

Line by line:
- `FROM python:3.12-slim AS builder` — names the first stage `builder`. `slim` is Debian bookworm with just Python, no build tools.
- `WORKDIR /build` — sets the working dir inside the stage.
- `COPY src/requirements.txt .` — copy just the requirements file first. Docker caches this layer; if requirements don't change, the pip install layer is reused on every build.
- `RUN pip install --no-cache-dir --prefix=/install -r requirements.txt` — installs packages into `/install` (not the default `/usr/local`). `--no-cache-dir` keeps pip from writing its wheel cache (which would bloat the layer).
- `FROM python:3.12-slim` — starts the final stage. Fresh, clean base.
- `COPY --from=builder /install /usr/local` — copies the installed packages from the builder stage into the final image's Python path. No pip, no build tools, no cache — just the installed packages.
- `COPY src/train.py .` — copies just the app code.
- `ENTRYPOINT ["python", "train.py"]` — the command. When k8s runs this image, it runs `python train.py`.

### The serving image Dockerfile (stage 05)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY src/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/app.py .
EXPOSE 8000
USER 1000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Two differences from the training image:
- `USER 1000` — runs as UID 1000 (non-root). k8s Pod Security Standards `restricted` requires this. If the container writes to a mounted volume, the volume must be writable by UID 1000.
- `CMD ["uvicorn", ...]` instead of ENTRYPOINT. CMD can be overridden by k8s Pod spec's `command`/`args`; ENTRYPOINT is harder to override. For a server, CMD is the convention.

### Why `--prefix=/install` + `COPY --from=builder`?
If you `pip install` into the default `/usr/local`, the install pulls in pip itself + setuptools + wheel + the cache. Copying `/install` (which is just the package trees) into the final stage's `/usr/local` gives you the packages without the installer bloat. It's the cleanest way to get a small Python image.

---

## 4. Image sizes — why we care

| Image | Size | What's in it |
|-------|------|--------------|
| `python:3.12` | ~1 GB | Full Debian + Python + build tools |
| `python:3.12-slim` | ~150 MB | Debian slim + Python (no build tools) |
| `python:3.12-alpine` | ~50 MB | Alpine + Python (musl libc, some packages don't work) |
| Our multi-stage sklearn image | ~200 MB | slim + installed sklearn/joblib/numpy (no pip, no cache) |

For a Mac running kind, every MB matters: `kind load docker-image` copies the image from Docker into the kind node container. A 1.5 GB image takes 30+ seconds to load; a 200 MB image loads in 5 seconds.

### Why not Alpine?
Alpine uses `musl` libc instead of `glibc`. Many Python wheels (numpy, scipy, pandas, sklearn) are built against glibc and won't work on Alpine without recompiling from source — which re-introduces build tools and defeats the size advantage. For ML, stick to `slim` (Debian-based).

---

## 5. `kind load docker-image` — the missing registry

On a real cluster you'd push to a registry (`docker push myregistry.com/myapp:v1`) and the Pod spec would reference that image. On kind there's no registry. Instead:

```bash
docker build -t iris-train:0.1 .
kind load docker-image iris-train:0.1
```

`kind load docker-image` takes the image from your Mac's Docker, packages it as a tar, and `docker exec`'s into the kind node container to `ctr images import` it. After that, the kind node's containerd has the image and Pods can use it.

In the Pod/Job/Deployment manifest, set `imagePullPolicy: Never` (or `IfNotPresent`) so kubelet doesn't try to pull from a registry — it just uses the local image.

```yaml
spec:
  containers:
  - name: train
    image: iris-train:0.1
    imagePullPolicy: IfNotPresent
```

> **Gotcha:** if you rebuild the image with the same tag (`iris-train:0.1`), you must re-run `kind load docker-image` — kind doesn't auto-sync. If the tag is `:latest`, set `imagePullPolicy: Never` to prevent kubelet from trying to pull (it always pulls `:latest` by default).

---

## 6. Running as non-root

Production k8s clusters enforce **Pod Security Standards** — the `restricted` level requires containers to run as non-root. Even on kind (which defaults to `privileged`), running as non-root is a good habit.

In the Dockerfile:
```dockerfile
USER 1000
```

This makes every process in the container run as UID 1000. Implications:
- The container can't write to `/root` or `/var/log`.
- If the app writes to a mounted PVC, the PVC's filesystem must allow UID 1000 to write. On kind's `local-path` StorageClass, the directory is created with mode 0777, so this works.

In the Pod spec (covered in stage 05), you can also set a `securityContext`:
```yaml
spec:
  securityContext:
    runAsUser: 1000
    runAsNonRoot: true
```

---

## 7. Config via env vars — the 12-factor pattern

The training script reads its config from env vars with sensible defaults:

```python
MODEL_PATH = os.environ.get("MODEL_PATH", "/data/model.joblib")
N_ESTIMATORS = int(os.environ.get("N_ESTIMATORS", "20"))
```

This lets you override config in the k8s manifest without rebuilding the image:

```yaml
spec:
  containers:
  - name: train
    image: iris-train:0.1
    env:
    - name: N_ESTIMATORS
      value: "50"
    - name: MODEL_PATH
      value: /data/model.joblib
```

This is the **12-factor app** pattern (config in the environment, not hardcoded). It's why k8s has ConfigMaps and Secrets — they inject env vars into Pods.

---

## 8. The build → load → run loop

The full cycle for any custom image on kind:

```
   edit code ──> docker build -t <name>:<tag> .
              ──> kind load docker-image <name>:<tag>
              ──> kubectl apply -f manifest.yaml   (image: <name>:<tag>, imagePullPolicy: IfNotPresent)
              ──> kubectl get pods  (watch it run)
```

If you edit the code, you rebuild with a **new tag** (or the same tag + re-load). If the Pod is managed by a Deployment, `kubectl rollout restart deployment/<name>` to force a re-pull.

---

## 9. What you should be able to explain after stage 03

- Why a single-stage Python image is bloated (pip cache, build tools).
- How a multi-stage Dockerfile works (builder stage + final stage, `COPY --from`).
- Why `python:3.12-slim` is the right base for ML (not alpine, not full).
- How `kind load docker-image` replaces a registry.
- Why `imagePullPolicy: IfNotPresent` is needed for local images.
- Why `USER 1000` matters for Pod Security.
- The 12-factor config pattern (env vars with defaults).

---

## 10. Further reading

- Docker multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- kind load docker-image: https://kind.sigs.k8s.io/docs/user/quick-start/#loading-an-image-into-the-cluster
- Kubernetes imagePullPolicy: https://kubernetes.io/docs/concepts/containers/images/
- Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- 12-factor app (config): https://12factor.net/config
- Slim Python images: https://hub.docker.com/_/python (see "Image variants" → slim)