# 05 — Lab: Serving a single model

> Read `concepts.md` first. The training Job (stage 04) must have run and the `model-pvc` must have the model.

---

## Objectives

1. Install metrics-server (required for HPA).
2. Deploy the serving app (2 replicas, PVC read-only, probes).
3. Expose via Service + Ingress (`serve.local`).
4. Verify probes, prediction endpoint, and DNS.
5. Add HPA and see it scale under load.
6. Clean up.

---

## 0. Prerequisites

- `iris-serve:0.1` image built and loaded (stage 03).
- `model-pvc` PVC exists with `model.joblib` on it (stage 04 ran successfully).
- `cloud-provider-kind` running (for Ingress external IP).

Verify:

```bash
kubectl get pvc model-pvc
kubectl exec kind-control-plane -- crictl images | grep iris-serve
```

Both should return results.

---

## 1. Install metrics-server

HPA needs CPU metrics. Install metrics-server:

```bash
kubectl apply -f manifests/metrics-server.yaml
kubectl wait --for=condition=Ready pod -l k8s-app=metrics-server -n kube-system --timeout=120s
```

Verify it's collecting metrics (may take 30s after Ready):

```bash
kubectl top nodes
```

Expected (after a few seconds):

```
NAME                 CPU(cores)   MEMORY(bytes)
kind-control-plane   150m         800Mi
```

If you see `error: metrics not available yet`, wait 30s and retry.

---

## 2. Deploy the serving app

```bash
kubectl apply -f manifests/deployment.yaml
kubectl apply -f manifests/service.yaml
kubectl wait --for=condition=Ready pod -l app=iris-serve --timeout=120s
```

### Check probes

```bash
kubectl describe pod -l app=iris-serve | grep -A2 "Liveness\|Readiness"
```

Expected (each probe section shows `last-probe` results):

```
Liveness:   http-get http://:8000/health delay=5s timeout=1s period=10s #success=1 #failure=3
Readiness:   http-get http://:8000/ready delay=3s timeout=1s period=5s #success=1 #failure=3
```

### Check endpoints

```bash
kubectl get endpoints iris-serve
```

Expected (2 endpoints — one per replica):

```
NAME         ENDPOINTS                       AGE
iris-serve   10.244.0.20:8000,10.244.0.21:8000   30s
```

If you see `<none>`, the readiness probe is failing. Check:

```bash
kubectl describe pod -l app=iris-serve | tail -10
```

---

## 3. Reach the app

### Option A: port-forward (simplest)

```bash
kubectl port-forward svc/iris-serve 8000:80
```

In another terminal:

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

### Option B: Ingress (needs cloud-provider-kind + /etc/hosts)

Apply the Ingress:

```bash
kubectl apply -f manifests/ingress.yaml
kubectl get ingress iris-serve
```

Get the Ingress IP:

```bash
INGRESS_IP=$(kubectl get ingress iris-serve -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo $INGRESS_IP
```

Add to `/etc/hosts` (needs `sudo`):

```bash
echo "$INGRESS_IP serve.local" | sudo tee -a /etc/hosts
```

Now:

```bash
curl http://serve.local/health
curl -X POST http://serve.local/predict \
  -H "Content-Type: application/json" \
  -d '{"sepal_length": 6.7, "sepal_width": 3.0, "petal_length": 5.0, "petal_width": 1.7}'
```

Expected (last curl — a versicolor sample):

```json
{"class_label": 1, "class_name": "versicolor"}
```

Clean up the `/etc/hosts` entry when done:

```bash
sudo sed -i '' '/serve.local/d' /etc/hosts
```

---

## 4. Add HPA

```bash
kubectl apply -f manifests/hpa.yaml
kubectl get hpa iris-serve
```

Expected:

```
NAME         REFERENCE               TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
iris-serve   Deployment/iris-serve   0%/70%    2         5         2          5s
```

`TARGETS: 0%/70%` means current CPU is 0% of the 70% target. The HPA will keep 2 replicas
(the min) since load is low.

### Generate load to see scaling

Open a terminal and hammer the endpoint (while port-forward is running):

```bash
for i in $(seq 1 1000); do
  curl -s -X POST http://localhost:8000/predict \
    -H "Content-Type: application/json" \
    -d '{"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}' > /dev/null
done
```

While that runs, in another terminal watch the HPA:

```bash
kubectl get hpa iris-serve -w
```

You should see `TARGETS` go up (CPU rises under load). If it crosses 70%, `REPLICAS` will
increase (up to 5). After the load stops, it'll scale back down after a few minutes (HPA
has a default 5-minute cooldown for scale-down).

> **Note:** On a single-node CPU-only kind cluster, generating enough CPU load to trigger
> scale-up can be tricky (the kind node has limited CPU). If HPA doesn't scale, try running
> the load loop in parallel (multiple terminals) or reduce `averageUtilization` to 10% in
> the HPA manifest temporarily. The point is to see the mechanism, not to hit a specific number.

---

## 5. Clean up

```bash
kubectl delete -f manifests/hpa.yaml
kubectl delete -f manifests/ingress.yaml
kubectl delete -f manifests/service.yaml
kubectl delete -f manifests/deployment.yaml
```

Keep the PVC and metrics-server for later stages:

```bash
kubectl get pvc model-pvc
kubectl get deployment metrics-server -n kube-system
```

Remove the `/etc/hosts` entry if you added one:

```bash
sudo sed -i '' '/serve.local/d' /etc/hosts
```

---

## 6. What "done" looks like

- `kubectl get deployment iris-serve` shows 2/2 Ready.
- `kubectl get endpoints iris-serve` shows 2 endpoints (readiness probe passed).
- `curl /predict` returns `{"class_label": 0, "class_name": "setosa"}`.
- `kubectl get hpa iris-serve` shows `TARGETS` with a CPU percentage.
- `kubectl top nodes` shows CPU/memory metrics (metrics-server works).
- You can explain the difference between liveness and readiness.

---

## Try next

`../06-gitops-argocd/` — declarative deploy of this serving app from git, sync waves, Argo CD UI.

---

## Troubleshooting

- **Pods `Running` but endpoints `<none>`** — readiness probe failing. Check
  `kubectl logs -l app=iris-serve` — likely "Model not found". Verify the PVC has the model
  (stage 04 Job must have run). `kubectl run debug --rm -it --image=alpine:3.21
  --overrides='...' -- ls /data` (see stage 04 README).
- **`kubectl top nodes` shows `metrics not available`** — metrics-server still starting. Wait
  30s and retry. If still failing: `kubectl logs -n kube-system -l k8s-app=metrics-server`.
- **HPA `TARGETS unknown`** — metrics-server not ready. Verify `kubectl top nodes` works first.
- **Ingress `ADDRESS <pending>`** — cloud-provider-kind not running. Start it (stage 00).
- **`curl serve.local` doesn't resolve** — you didn't add it to `/etc/hosts`. See step 3B.