# 01 — Concepts: Pods, Deployments, Services, Labels

> Read this first. Then run the lab in `README.md`.
> Verified against k8s v1.36 docs (kubernetes.io/docs/concepts/workloads/pods/,
> /controllers/deployment/, /services-networking/service/) — all APIs stable: `v1`, `apps/v1`.

---

## 1. The Pod — k8s's smallest deployable unit

### What it is
A **Pod** is a group of 1+ containers that:
- Run on the same node.
- Share the same network namespace (same IP, same port space).
- Share the same volumes (storage).
- Are scheduled, started, stopped, and die **together**.

Think of a Pod as a "logical host" for your app. If two containers must always co-locate
(share localhost or a file), they belong in the same Pod. If they don't, they belong in
separate Pods.

### Why Pods exist (not just "containers")
k8s doesn't run containers directly — it runs Pods that wrap containers. This extra layer:
- Lets you co-locate cooperating containers (e.g. app + log sidecar) with shared network/volumes.
- Gives the scheduler a unit to place (it places Pods, not individual containers).
- Provides a stable identity for the workload inside, even as the underlying container restarts.

### Key facts
- Each Pod gets a unique IP (in the pod CIDR, e.g. `10.244.0.12`). All containers in the Pod share that IP.
- A Pod's IP is **ephemeral** — it changes when the Pod is recreated. Never hardcode it.
- Pods are **mortal**. They don't self-heal. If a node dies or a container crashes, that specific Pod is gone. The thing that re-creates Pods is a controller (ReplicaSet, Job, etc.) — see §3.
- You almost never create a Pod directly with a manifest. You create a Deployment, which creates a ReplicaSet, which creates Pods. But understanding the Pod manifest is foundational.

### The Pod manifest, field by field

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  containers:
  - name: nginx
    image: nginx:1.27
    ports:
    - containerPort: 80
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 200m
        memory: 256Mi
```

- `apiVersion: v1` — the core k8s API. Stable since the beginning.
- `kind: Pod` — the resource type.
- `metadata.name` — must be unique within the namespace.
- `metadata.labels` — key/value tags used by selectors (see §5). Crucial for Services.
- `spec.containers[]` — the container(s). `image` is pulled by containerd. `ports.containerPort` is informational (it doesn't actually open a port — the container does that); k8s uses it for health checks and documentation.
- `spec.containers[].resources` — **requests** (guaranteed minimum, used for scheduling) vs **limits** (max allowed, enforced by cgroups). Always set these in production.

### Pod lifecycle (compressed)
1. Pending → scheduler picks a node → kubelet starts containers.
2. Running → container process is alive.
3. Succeeded / Failed → terminal (only for `restartPolicy: Never/OnFailure`, used by Jobs).
4. For the default `restartPolicy: Always` (Deployments), a crashed container is restarted by kubelet. The Pod object stays the same; the container restart counter increments.

---

## 2. The Deployment — "I want N replicas of this Pod, rolled out and updated"

### What it is
A **Deployment** is a higher-level controller. You describe:
- A Pod template (image, ports, env, etc.).
- How many replicas you want.
- An update strategy (RollingUpdate by default).

The Deployment controller creates a **ReplicaSet**, which creates N Pods. When you change
the Pod template (e.g. new image tag), the Deployment creates a **new** ReplicaSet and
scales it up while scaling the old one down — a rolling update.

### The hierarchy you must memorize

```
Deployment  ──manages──>  ReplicaSet (v1)  ──manages──>  Pod (× N)
            ──manages──>  ReplicaSet (v2)  ──manages──>  Pod (× N)   ← after a rollout
            ──manages──>  ReplicaSet (v1)  [scaled to 0, kept for rollback]
```

Why keep the old ReplicaSet at 0 replicas? **Rollback.** `kubectl rollout undo deployment/nginx` scales v1 back up and v2 down. The history is in `kubectl rollout history deployment/nginx`.

### The Deployment manifest, field by field

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx-deploy
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nginx
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:1.27
        ports:
        - containerPort: 80
```

- `apiVersion: apps/v1` — the workload API. Pod was `v1`; Deployments live in `apps/v1`.
- `spec.replicas` — desired number of Pods. The ReplicaSet keeps this true.
- `spec.selector.matchLabels` — **which Pods this Deployment owns**. Must match `template.metadata.labels`. If they don't match, the Deployment controls nothing. This is the most common beginner bug.
- `spec.strategy.rollingUpdate`:
  - `maxSurge: 1` — during a rollout, can have at most 1 Pod **above** `replicas` at a time.
  - `maxUnavailable: 0` — can have 0 Pods below `replicas` during rollout (zero-downtime).
  - Set `maxUnavailable: 1` instead if you can tolerate brief capacity loss but want fewer total Pods.
- `spec.template` — the Pod template. Every Pod the ReplicaSet creates is stamped from this.

### Imperative shortcuts (useful for quick tests)
- `kubectl create deployment nginx --image=nginx:1.27 --replicas=3` — generates a Deployment on the fly. No YAML needed. Good for experimentation; bad for GitOps (no source of truth).
- `kubectl scale deployment/nginx --replicas=5` — imperative scaling. Kicks the reconcile loop.
- `kubectl set image deployment/nginx nginx=nginx:1.28` — imperative image bump, triggers a rolling update.

---

## 3. The ReplicaSet — "keep exactly N copies alive"

You usually don't write ReplicaSet manifests directly — the Deployment does it for you.
But you should know what it does:

- Watches the Pods that match its selector.
- Counts them.
- If count < N → creates Pods from the template.
- If count > N → deletes extras (random choice, or by a deletion policy).

The ReplicaSet is the thing that notices when a Pod dies and **recreates it**. That's the
"self-healing" property of Deployments: it's not magic, it's the ReplicaSet counting Pods
every few seconds and reconciling.

You can see ReplicaSets with `kubectl get rs`. The Deployment owns them; deleting a
ReplicaSet by hand will just have the Deployment re-create it. Don't fight it.

---

## 4. The Service — a stable name + IP that routes to a set of Pods

### The problem it solves
A Pod's IP changes on every restart. Other pods can't keep a connection to it.
A **Service** is a stable IP + DNS name that load-balances across the matching Pods.

```
   caller ──> Service (stable IP, DNS name) ──> Pod1 (10.244.0.5)
                                          └─> Pod2 (10.244.0.6)
                                          └─> Pod3 (10.244.0.7)
```

Pods come and go; the Service's IP stays. Behind the scenes, kube-proxy updates iptables/IPVS
rules on every node so packets sent to the Service IP get DNAT'd to a healthy Pod.

### The Service manifest, field by field

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx-svc
spec:
  type: ClusterIP
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
    protocol: TCP
```

- `spec.type: ClusterIP` — exposes the Service only inside the cluster. Default.
- `spec.selector` — picks which Pods this Service routes to. **Same label as the Pod template**. This is how Services and Pods are connected: by label, not by name.
- `spec.ports[].port` — the port the Service listens on (the port callers use).
- `spec.ports[].targetPort` — the port on the Pod's container (the port the app listens on). Can be a number or a named port.

### The four Service types (memorize this table)

| Type           | Reachable from            | How                                                                 |
|----------------|---------------------------|---------------------------------------------------------------------|
| **ClusterIP**  | Inside the cluster only   | Gets a virtual IP from the service CIDR. kube-proxy programs rules. |
| **NodePort**   | Outside, on any node's IP | Opens a port in range 30000–32767 on every node. Built on ClusterIP.|
| **LoadBalancer**| Outside, via a cloud LB   | Cloud provider provisions a LB pointing at the NodePort. External IP assigned. |
| **ExternalName** | Inside, but as a DNS alias | Returns a CNAME to an external DNS name (e.g. `mydb.rds.amazonaws.com`). No proxying. |

You almost always start with `ClusterIP` and only expose what truly needs to be public.
For HTTP apps in our kind cluster, **Ingress** (stage 00) is the production-grade way to
expose many Services through one external IP.

### DNS — why Services have names, not just IPs
CoreDNS (running in `kube-system`) creates a DNS record for every Service:
`<service-name>.<namespace>.svc.cluster.local`. Pods in the same namespace can just use
`<service-name>` — that resolves to the Service's ClusterIP. This is how one Pod calls
another: by Service name, never by Pod IP.

Example: a FastAPI app calling Redis uses `redis-svc:6379`, not `10.244.0.12:6379`.

---

## 5. Labels and Selectors — the connective tissue of k8s

### What labels are
Labels are key/value pairs attached to **any** k8s object. They're for **identification and
grouping**, not for configuration (use annotations for that).

```yaml
metadata:
  labels:
    app: nginx
    tier: frontend
    env: prod
```

### What selectors are
Selectors are queries over labels. Two flavors:

- **Equality-based**: `app=nginx`, `env!=dev`
- **Set-based**: `app in (nginx, api)`, `tier notin (debug)`

Used in three key places:
1. **Deployment.spec.selector** — which Pods it owns.
2. **Service.spec.selector** — which Pods it routes to.
3. **`kubectl get pods -l app=nginx`** — filtering on the CLI.

### The connection pattern (draw this)

```
   Deployment         Service
   selector:            selector:
     app: nginx           app: nginx
        │                    │
        │ creates Pods with  │ selects Pods with
        │   label app=nginx  │   label app=nginx
        ▼                    ▼
        ┌──────────────────────┐
        │  Pod (app=nginx)     │
        │  Pod (app=nginx)     │
        │  Pod (app=nginx)     │
        └──────────────────────┘
```

The Deployment and the Service both reference the **same label** (`app: nginx`). The
Deployment *writes* the label onto the Pods (via its template). The Service *reads* the
label to find Pods to route to. They never reference each other directly. This decoupling
is the whole point — you can swap the Deployment, scale it, roll it, and the Service
keeps working as long as some Pods match.

### Recommended labels (k8s convention)
The k8s docs recommend a common set (see `kubectl explain` for any resource):
- `app` — the app name
- `tier` — architectural layer (frontend/backend/cache)
- `env` — environment (dev/staging/prod)
- `version` — image version, for canary/rollback

We'll mostly use `app` and a custom `stage` label later (for MLflow model stage).

---

## 6. Namespace revisited

We met namespaces in stage 00. Quick recap for this stage:

- A namespace is a scoping boundary for names. `nginx-deploy` in `default` and
  `nginx-deploy` in `mlflow` are two different Deployments.
- Resources in one namespace can reference Services in another using the full DNS name:
  `redis-svc.mlflow.svc.cluster.local`.
- Namespaces are created with `kubectl create ns <name>` or a manifest.
- Most `kubectl` commands default to the `default` namespace unless you pass `-n <ns>`.

In stage 01 we'll keep things in `default` to keep commands short. Later stages move to
dedicated namespaces (`mlflow`, `kubeflow`, etc.) to mirror production hygiene.

---

## 7. The mental model that ties it together

When you `kubectl apply -f deployment.yaml` for a 3-replica nginx Deployment + a ClusterIP
Service, here's the full chain:

1. **You** → API server: "store this Deployment"
2. **Deployment controller** sees it → creates a **ReplicaSet** (revision 1)
3. **ReplicaSet controller** sees the ReplicaSet → wants 3 Pods → creates 3 **Pod objects**
4. **Scheduler** sees 3 unscheduled Pods → assigns each to a node (here: all to
   `kind-control-plane`, our only node) → writes `nodeName`
5. **Kubelet** on the node sees 3 new Pods assigned to it → calls containerd → pulls
   `nginx:1.27` → starts 3 containers → reports Running back to the API server
6. **You** → `kubectl apply -f service.yaml` → API server stores the Service
7. **Endpoints controller** (and EndpointSlice controller) sees the Service's selector
   (`app=nginx`) → looks up matching Pods → writes their IPs into an EndpointSlice
8. **kube-proxy** on each node sees the EndpointSlice → programs iptables/IPVS rules →
   from now on, sending a packet to the Service's ClusterIP DNATs to one of the 3 Pod IPs
9. **CoreDNS** sees the new Service → adds an A record `<svc>.<ns>.svc.cluster.local`
   pointing at the ClusterIP
10. Any Pod in the cluster can now `curl http://nginx-svc` and get a response from one of
    the 3 nginx Pods, load-balanced round-robin

Every step is a separate controller watching etcd and reacting. There's no "main loop"
that runs the show — that's why k8s is resilient and extensible.

---

## 8. What you should be able to explain after stage 01

- What a Pod is and why it exists (not just "a container wrapper").
- The Deployment → ReplicaSet → Pod hierarchy and what each layer adds.
- Why Pod IPs are ephemeral and what a Service does about it.
- The four Service types and when to use each.
- How Labels + Selectors connect Deployments, Pods, and Services (draw the diagram).
- What `kubectl apply`, `kubectl scale`, `kubectl rollout` do to the reconcile loop.
- Why DNS works inside a cluster (`nginx-svc` resolves to the ClusterIP).
- The full chain from `apply` to "curl works" (§7).

---

## 9. Further reading (official docs)

- Pods: https://kubernetes.io/docs/concepts/workloads/pods/
- Pod lifecycle: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
- Deployment: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- ReplicaSet: https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/
- Service: https://kubernetes.io/docs/concepts/services-networking/service/
- Labels and Selectors: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/
- DNS for Services: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- Run a stateless app with a Deployment: https://kubernetes.io/docs/tasks/run-application/run-stateless-application-deployment/
- Connect a frontend to a backend using Services: https://kubernetes.io/docs/tasks/access-application-cluster/connecting-frontend-backend/