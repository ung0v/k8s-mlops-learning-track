# 05 — Concepts: Serving a single model

> Read this first. Then run the lab in `README.md`.
> Verified against k8s v1.36 docs — Deployment `apps/v1`, Service `v1`, Ingress `networking.k8s.io/v1`,
> HPA `autoscaling/v2`, probes (Pod spec `v1`).

---

## 1. What "serving" means in MLOps

Training (stage 04) produces a model artifact. **Serving** loads that artifact and exposes
it as an API so other systems can get predictions. The lifecycle:

```
   train (Job) ──> model.joblib on PVC
                ──> serving Pod loads model at startup
                ──> FastAPI listens on :8000
                ──> POST /predict {features} ──> {class_label, class_name}
```

This stage is a Deployment (the serving Pod should always be running), not a Job. We add:
- **Probes** (liveness + readiness) so k8s knows when the Pod is healthy.
- **HPA** (HorizontalPodAutoscaler) to scale replicas based on CPU.
- **Ingress** to route HTTP traffic from outside the cluster to the Service.

---

## 2. Probes — liveness vs readiness vs startup

Probes tell k8s about the Pod's health. Three types:

### Liveness probe
"Is the Pod alive?" If this fails, k8s **restarts the container**.
- Use for: detecting deadlocks, infinite loops, memory leaks that make the app unresponsive.
- Don't use for: checking if the model loaded — that's readiness.
- Endpoint for our app: `GET /health` (returns 200 if the process is alive).

### Readiness probe
"Is the Pod ready to serve traffic?" If this fails, k8s **removes the Pod from the Service's
endpoints** (stops sending it requests) but does NOT restart it.
- Use for: "the model is loaded and I can serve predictions."
- Critical for rolling updates: a new Pod must pass readiness before the old Pod is removed.
- Endpoint for our app: `GET /ready` (returns 200 only after `load_model()` succeeds).

### Startup probe
"Has the app finished starting up?" If this is set, liveness/readiness don't run until startup
passes. Useful for apps with slow startup (loading a large model into memory).
- We don't strictly need it here (iris model loads in <1s), but for LLMs (stage 12) it's essential.

### The manifest

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 3
  periodSeconds: 5
```

- `initialDelaySeconds` — wait this long before the first probe. Gives the app time to start.
- `periodSeconds` — how often to probe.
- `failureThreshold` — after this many consecutive failures, k8s considers the probe failed (default 3).

### Why our app has separate `/health` and `/ready`
- `/health` always returns 200 if uvicorn is running. It's for liveness (process is alive).
- `/ready` returns 200 only if the model loaded successfully. It's for readiness (can serve).
- If the model file is missing, `/ready` fails → Pod stays out of the Service endpoints →
  no traffic reaches it → users don't see 500 errors. This is the right behavior.

---

## 3. The HorizontalPodAutoscaler (HPA)

HPA automatically scales the number of replicas based on observed metrics.

### The manifest

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: iris-serve
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: iris-serve
  minReplicas: 2
  maxReplicas: 5
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

- `scaleTargetRef` — what to scale (the Deployment named `iris-serve`).
- `minReplicas: 2` — never scale below 2 (availability).
- `maxReplicas: 5` — never scale above 5 (cost control).
- `averageUtilization: 70` — if average CPU across pods > 70%, scale up; if < 70%, scale down.

### How HPA works (the loop)
1. HPA controller polls the metrics API every 15s for the Deployment's CPU usage.
2. If avg CPU > 70%, it calculates the desired replicas: `ceil(current * (current_cpu / target_cpu))`.
3. It patches the Deployment's `spec.replicas` to that number.
4. The Deployment's ReplicaSet creates/removes Pods to match.
5. Repeat.

### Prerequisite: metrics-server
HPA needs the **metrics-server** to provide CPU/memory metrics. kind doesn't ship with it by
default. We'll install it in the lab (it's a single manifest apply). Without it, HPA shows
`unknown` metrics and never scales.

---

## 4. Ingress — HTTP routing to the Service

Ingress is the L7 (HTTP) way to expose a Service. We met it in stage 00 (cloud-provider-kind
handles it natively). Here we create an Ingress object that routes `serve.local/` to the
`iris-serve` Service.

### The manifest

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: iris-serve
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: serve.local
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: iris-serve
            port:
              number: 80
```

- `host: serve.local` — the hostname clients will use. You need to add `127.0.0.1 serve.local`
  (or the Ingress IP) to `/etc/hosts` on your Mac.
- `pathType: Prefix` — match any path starting with `/` (i.e. everything).
- `backend.service` — which Service to route to (`iris-serve` on port 80).

> **Note:** cloud-provider-kind assigns an external IP to the Ingress. The Ingress class is
> `cloud-provider-kind` (set automatically). You don't need to specify `ingressClassName`
> because cloud-provider-kind watches all Ingresses without a class by default.

---

## 5. The full manifest stack for serving

```
   Ingress (serve.local) ──routes to──> Service (iris-serve, ClusterIP)
                                         │
                                         ▼
                                    Deployment (iris-serve, replicas: 2)
                                         │ manages
                                    ReplicaSet
                                         │ creates
                                    Pod ── mounts PVC (model-pvc, read-only)
                                    Pod ── runs uvicorn app:app
                                         ▲
                                    HPA watches CPU, scales 2–5
```

Resources:
- **PVC** (created in stage 04) — holds `model.joblib`.
- **Deployment** — 2 replicas, mounts the PVC read-only, runs `iris-serve:0.1`.
- **Service** — ClusterIP, port 80 → targetPort 8000.
- **Ingress** — routes `serve.local` to the Service.
- **HPA** — scales 2–5 based on CPU.

---

## 6. What you should be able to explain after stage 05

- The difference between liveness and readiness probes, and why each matters.
- Why `/ready` returning 500 (model not loaded) removes the Pod from the Service.
- How HPA decides to scale up or down (CPU > target → scale up).
- Why metrics-server is required for HPA.
- What Ingress does that a LoadBalancer Service doesn't (L7 routing by host header).
- The full chain: Ingress → Service → Deployment → Pod → PVC → model.

---

## 7. Further reading

- Probes: https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Configure probes: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/
- HPA walkthrough: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale-walkthrough/
- HPA reference: https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/horizontal-pod-autoscaler-v2/
- Ingress: https://kubernetes.io/docs/concepts/services-networking/ingress/
- metrics-server: https://github.com/kubernetes-sigs/metrics-server