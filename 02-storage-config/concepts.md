# 02 — Concepts: Storage, Config, and StatefulSets

> Read this first. Then run the lab in `README.md`.
> Verified against k8s v1.36 docs — all APIs stable: PV/PVC `v1`, StatefulSet `apps/v1`,
> ConfigMap `v1`, Secret `v1`, init containers (Pod spec `v1`).

---

## 1. Why Pods need storage and config

Stage 01's nginx Pods were stateless: no data mattered, no config varied. Real apps need:

- **Persistent data** — a database writes files that must survive Pod restarts.
- **Configuration** — an app reads a config file or env vars (DB host, log level, model path).
- **Secrets** — passwords, API keys, TLS certs — must not be in plaintext YAML or env vars.

Kubernetes gives you three resource types + a workload controller for stateful apps:
- **PersistentVolume (PV)** + **PersistentVolumeClaim (PVC)** — durable storage.
- **ConfigMap** — non-secret config, injected as env vars or files.
- **Secret** — sensitive data, same injection mechanisms, base64-encoded (not encrypted by default).
- **StatefulSet** — a controller that gives each Pod a stable identity + its own volume.

---

## 2. Volumes vs PersistentVolumes — two storage concepts

### Volumes (ephemeral, tied to Pod lifetime)
A **Volume** is defined inline in the Pod spec. It lives as long as the Pod. Common types:
- `emptyDir` — scratch space on the node. Wiped when the Pod dies. Good for sharing data between containers in the same Pod.
- `hostPath` — mounts a file/dir from the host node. Dangerous in prod (couples Pod to node), useful for debugging.
- `configMap` / `secret` — projects ConfigMap/Secret data as files.

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /scratch
  volumes:
  - name: data
    emptyDir: {}
```

### PersistentVolumes (durable, independent of Pod)
A **PersistentVolume (PV)** is a cluster-level storage resource. It outlives any Pod.
A **PersistentVolumeClaim (PVC)** is a user's request for storage: "I want 5Gi, ReadWriteOnce".

Think of it as the cloud computing pattern:
- **PV** = the actual disk (provisioned by an admin or dynamically by a StorageClass).
- **PVC** = a claim ticket that says "give me a disk matching these requirements".
- The Pod mounts the **PVC**, not the PV directly.

```
   admin/cloud ─creates─> PV (real disk)
                         ↑ bound to
   user ─creates─> PVC (claim: 5Gi RWO)
                    ↑ mounted by
   Pod spec ─references─> PVC
```

### Access modes (memorize)
- `ReadWriteOnce` (RWO) — one node can read/write. Most common for single-node kind.
- `ReadOnlyMany` (ROX) — many nodes can read. Good for shared read-only data.
- `ReadWriteMany` (RWX) — many nodes can read/write. Needs NFS or a distributed FS.
- `ReadWriteOncePod` (RWOP) — only one **Pod** can mount it (stronger than RWO).

> **Note:** kind ships with a `standard` StorageClass (provisioner `rancher.io/local-path`)
> that provisions hostPath-based PVs dynamically. It uses `WaitForFirstConsumer` binding
> (delays binding until a Pod is scheduled, so the volume lands on the right node). If you
> don't specify `storageClassName`, k8s uses the default (which is `standard` in kind).

### Reclaim policies
- `Retain` — when PVC is deleted, PV stays around with its data. Manual cleanup.
- `Delete` (default for dynamic provisioning) — when PVC is deleted, PV + data are deleted.

### The PVC manifest

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-pvc
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 1Gi
```

The Pod references it by name:

```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /data
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: data-pvc
```

---

## 3. ConfigMap — inject config without rebuilding the image

A **ConfigMap** is a key-value store for non-sensitive config. Three ways to inject:

### (a) As environment variables
```yaml
spec:
  containers:
  - name: app
    env:
    - name: LOG_LEVEL
      valueFrom:
        configMapKeyRef:
          name: app-config
          key: log_level
```

### (b) As a single env block (envFrom)
```yaml
spec:
  containers:
  - name: app
    envFrom:
    - configMapRef:
        name: app-config
```
All keys become env vars. Convenient but no control over naming.

### (c) As files mounted in a volume
```yaml
spec:
  containers:
  - name: app
    volumeMounts:
    - name: config
      mountPath: /etc/config
      readOnly: true
  volumes:
  - name: config
    configMap:
      name: app-config
```
Each key becomes a file; the file's content is the key's value. Best for config files
the app reads (nginx.conf, application.yml). Updates to the ConfigMap propagate to the
mounted files within ~1 minute (kubelet syncs) — but env-var injection requires a Pod restart.

### The ConfigMap manifest

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  log_level: "info"
  app.properties: |
    color.good=purple
    color.bad=yellow
    allow.textmode=true
```

Two keys: `log_level` (a string) and `app.properties` (a multi-line string that becomes a file).

---

## 4. Secret — same as ConfigMap but for sensitive data

A **Secret** is structurally identical to a ConfigMap but:
- Values are base64-encoded (so binary data like TLS certs work).
- Not encrypted at rest by default (enable encryption-at-rest in the API server for that).
- Mounted in a tmpfs (RAM) by default, not written to disk on the node.
- Can be restricted by RBAC separately from ConfigMaps.

> **Gotcha:** base64 is NOT encryption. Anyone with `kubectl get secret -o yaml` can decode it.
> Real secret management needs external secret stores (Vault, AWS Secrets Manager, Sealed Secrets, etc.).

### Creating a Secret
The cleanest way is to create it from literal values:

```bash
kubectl create secret generic db-secret \
  --from-literal=username=admin \
  --from-literal=password='s3cr3t!'
```

Or from a manifest (you must base64-encode yourself — `echo -n 's3cr3t!' | base64`):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-secret
type: Opaque
data:
  username: YWRtaW4=          # base64('admin')
  password: czNjcjN0IQ==      # base64('s3cr3t!')
```

### Injecting secrets
Same three ways as ConfigMaps: `env` + `secretKeyRef`, `envFrom` + `secretRef`, or as a volume.

---

## 5. StatefulSet — the right tool for stateful, identity-aware workloads

### Why not just a Deployment for databases?
A Deployment creates interchangeable Pods: `nginx-7c4b-abc`, `nginx-7c4b-def`, ...
None has a stable identity. When one dies, a new one with a new name and new IP replaces it.
That's fine for stateless apps, but bad for:
- **Databases** — each replica needs its own data, and a stable name peers use to find it.
- **Distributed systems** — ZooKeeper, etcd, Kafka: each node has an identity, joins a cluster by name.

### What a StatefulSet gives you
- **Stable, predictable Pod names**: `web-0`, `web-1`, `web-2` (not random hashes).
- **Stable DNS**: each Pod gets a DNS record `web-0.web-svc.default.svc.cluster.local`.
- **Stable storage**: each Pod gets its own PVC (via `volumeClaimTemplates`), and when the Pod is
  rescheduled, it reattaches to the same PVC — the data follows the identity, not the Pod.
- **Ordered startup and teardown**: Pods are created in order 0→1→2, deleted in reverse 2→1→0.
  Useful when Pod 1 needs Pod 0 to be ready first (e.g. primary then replicas).

### StatefulSet vs Deployment (memorize this table)

| Property            | Deployment                | StatefulSet                          |
|---------------------|---------------------------|--------------------------------------|
| Pod names           | `<deploy>-<rs>-<rand>`    | `<statefulset>-<ordinal>`            |
| Pod identity        | Interchangeable           | Each Pod has a stable name + DNS      |
| Storage             | Shared PVC (all replicas) | One PVC per replica (volumeClaimTemplates) |
| Startup order       | Parallel                  | Sequential (0,1,2...)                 |
| Network identity    | Service load-balances     | Each Pod has its own DNS A record     |
| Use case            | Stateless web apps        | Databases, distributed systems       |

### The StatefulSet manifest

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: web
spec:
  serviceName: web-svc          # the headless Service that gives Pods DNS names
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
      - name: nginx
        image: nginx:1.27
        ports:
        - containerPort: 80
        volumeMounts:
        - name: www
          mountPath: /usr/share/nginx/html
  volumeClaimTemplates:        # each Pod gets its own PVC from this template
  - metadata:
      name: www
    spec:
      accessModes: [ReadWriteOnce]
      storageClassName: local-path
      resources:
        requests:
          storage: 100Mi
```

Two things differ from a Deployment:
- `serviceName: web-svc` — names the **headless Service** (clusterIP: None) that backs this StatefulSet.
  A headless Service doesn't load-balance — it returns the Pod IPs directly, so clients can
  address `web-0` or `web-1` by name.
- `volumeClaimTemplates` — each replica gets its own PVC: `www-web-0`, `www-web-1`, `www-web-2`.
  When `web-1` is rescheduled to a different node, it reattaches to `www-web-1` — same data.

### Headless Service (the partner of a StatefulSet)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web-svc
spec:
  clusterIP: None          # this is what makes it "headless"
  selector:
    app: web
  ports:
  - port: 80
```

`clusterIP: None` tells k8s: "don't assign a virtual IP and don't load-balance. Just give me
DNS A records for each Pod." Now `web-0.web-svc` resolves to `web-0`'s IP, and `web-svc` resolves
to all three (round-robin at the DNS level).

---

## 6. Init containers — run something before the main app starts

An **init container** runs to completion before the main containers start. Use cases:
- Pre-populate a volume (download a model, generate a config).
- Wait for a dependency to be ready (e.g. wait for the DB Pod's port to respond).
- Run a setup script with different tools/permissions than the main container.

```yaml
spec:
  initContainers:
  - name: init
    image: busybox:1.36
    command: ['sh', '-c', 'echo "hello from init" > /data/index.html']
    volumeMounts:
    - name: www
      mountPath: /data
  containers:
  - name: nginx
    image: nginx:1.27
    volumeMounts:
    - name: www
      mountPath: /usr/share/nginx/html
  volumes:
  - name: www
    emptyDir: {}
```

The init container writes `index.html` into the shared `www` volume. The main nginx container
serves it. Init containers run **sequentially** and must all succeed before the main container starts.

---

## 7. The mental model that ties it together

When you `kubectl apply -f statefulset.yaml` with a `volumeClaimTemplates`:

1. **StatefulSet controller** creates Pod `web-0` first.
2. **PVC controller** sees the `volumeClaimTemplates`, creates PVC `www-web-0`.
3. **StorageClass** (`local-path`) provisions a PV (a directory on the kind node) and binds the PVC.
4. **Scheduler** places `web-0` on a node.
5. **Kubelet** mounts the PV into `web-0`, starts nginx.
6. Once `web-0` is Ready, the controller creates `web-1`. Same PVC creation flow.
7. Then `web-2`. (Sequential, not parallel — that's StatefulSet semantics.)
8. **Headless Service** `web-svc` gives each Pod a DNS A record.
9. If `web-1`'s Pod dies, the StatefulSet creates a **new** Pod named `web-1` (same name!),
   reattaches the **same** PVC `www-web-1`, and the data is back.

Compare to a Deployment: a dead Pod is replaced by a Pod with a new name, no specific storage,
no specific identity. That's why Deployments are for stateless, StatefulSets for stateful.

---

## 8. What you should be able to explain after stage 02

- The difference between a Volume (ephemeral) and a PersistentVolume (durable).
- What a PVC is and how a Pod references it.
- The three ways to inject a ConfigMap into a Pod (env, envFrom, volume).
- Why Secrets exist separately from ConfigMaps (base64, tmpfs, RBAC).
- Why base64 is not encryption (and what you'd need for real secret management).
- When to use a StatefulSet vs a Deployment.
- What a headless Service is and why StatefulSets need one.
- What an init container does and a real use case for it.
- Why deleting a StatefulSet Pod creates a new Pod with the **same name** (stable identity).

---

## 9. Further reading (official docs)

- Persistent Volumes: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Storage Classes: https://kubernetes.io/docs/concepts/storage/storage-classes/
- Dynamic volume provisioning: https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/
- Configure a Pod to use a PersistentVolume: https://kubernetes.io/docs/tasks/configure-pod-container/configure-volume-storage/
- StatefulSets: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/
- StatefulSet basics tutorial: https://kubernetes.io/docs/tutorials/stateful-application/basic-stateful-set/
- ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Configure a Pod to use a ConfigMap: https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/
- Secrets: https://kubernetes.io/docs/concepts/configuration/secret/
- Init containers: https://kubernetes.io/docs/concepts/workloads/pods/init-containers/
- Volumes (all types): https://kubernetes.io/docs/concepts/storage/volumes/