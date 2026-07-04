# 00 — Existing Flask Baseline (pre-curriculum snapshot)

These files existed **before** the curriculum was set up. They are kept here as a reference for what you already had — not a teaching stage. Skip ahead to `00-bootstrap`.

## Contents

- `app.py` — Flask "make change" app (the original hello-world you started from).
- `Dockerfile` — single-stage image on `python:3.8.8-slim-buster`.
- `kube-hello-change.yaml` — combined Service + Deployment (3 replicas) for the flask app.
- `deployment.yaml` — generic 3-replica nginx Deployment (root-level, pre-curriculum).
- `requirements.txt`, `test_app.py`, `Makefile`, `README.md` — supporting files from the original repo.

## What to notice before moving on

- `kube-hello-change.yaml` uses `imagePullPolicy: Never` because the image is loaded locally via `kind load docker-image` — there is no registry.
- Service `type: LoadBalancer` on kind won't get an external IP; on kind you reach it via `kubectl port-forward` or via ingress (set up in `00-bootstrap`).
- `Dockerfile` is single-stage and based on an old Python image — stages 03 and 05 will modernize this pattern.

## Build & run (optional, for nostalgia)

```bash
cd 00-existing-flask-baseline/kubernetes-hello-world-python-flask
docker build -t flask-change:latest .
kind load docker-image flask-change:latest
kubectl apply -f kube-hello-change.yaml
kubectl port-forward svc/hello-flask-change-service 8080:8080
# then: curl http://localhost:8080/change/1/37
```

## Next

Go to `../00-bootstrap/` to set up the cluster baseline used by every later stage.