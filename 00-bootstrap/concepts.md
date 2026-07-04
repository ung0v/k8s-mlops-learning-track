# 00 — Concepts: Kubernetes architecture & cluster fundamentals

> Read this **before** running the commands in `README.md`. This is the "why" and "what".
> The README is the "how". Together they form one lesson.

---

## 1. What problem does Kubernetes solve?

Imagine you have a Python Flask app. On your laptop you run it with `python app.py`.
In production you need:

- **Multiple copies** running at once (so one dying doesn't take down the site).
- **Automatic restart** when a copy crashes.
- **Scaling** up/down based on load.
- **Rolling updates** (new version with zero downtime).
- **Networking** between copies and to the outside world.
- **Same app on 50 machines** without SSH-ing into each one.

You *could* write bash scripts + systemd units + a load balancer config to do all this.
Or you could use a system built for exactly this: **Kubernetes (k8s)**.

Kubernetes is a **container orchestrator**: it decides which containers run where, keeps
them healthy, networks them, and scales them — declaratively. You describe the *desired
state* ("I want 3 nginx pods"); k8s continuously works to make reality match that desire.

---

## 2. The declarative model (the single most important idea)

Kubernetes is **declarative**, not imperative.

| Style       | Example                                              | Who acts                |
|-------------|------------------------------------------------------|-------------------------|
| Imperative  | "Start nginx on node-2 now"                          | You, manually           |
| Declarative | "I want 3 nginx pods running at all times"           | k8s, continuously       |

You write YAML describing the **desired state** and hand it to the k8s API. A controller
inside k8s notices the difference between desired and actual, and **reconciles** —
spawns pods, kills extras, restarts dead ones. If a node catches fire, k8s notices the
pods are gone and re-schedules them elsewhere. You don't tell it to.

This reconciliation loop is the heart of k8s. Every resource (Pod, Deployment, Service,
Ingress, Job, ...) is managed this way. Memorize this pattern:

```
   you ──apply YAML──> API server ──writes to──> etcd
                                            │
                                            ▼
                        controller watches etcd
                                            │
                          notices diff vs reality
                                            │
                            acts (creates/deletes pods)
                                            │
                                  reality changes
                                            │
                          controller re-watches, loops
```

---

## 3. Cluster architecture: control plane vs worker nodes

A k8s **cluster** is a set of machines that run your containers. Split into two roles:

### Control plane (the "brain")
- **API server** — the front door. Everything (`kubectl`, controllers, kubelets) talks to
  it over HTTPS. It validates requests and writes to etcd.
- **etcd** — a distributed key-value store. The **single source of truth** for cluster
  state. If etcd is gone, the cluster has amnesia.
- **scheduler** — decides *which node* a new Pod goes onto (based on resources, labels,
  taints).
- **controller manager** — runs the reconciliation loops for built-in resources
  (ReplicaSet, Deployment, Job, Service, etc.).
- **cloud-controller-manager** — bridges to cloud providers (AWS/GCP/Azure) and to
  **cloud-provider-kind** in our case. It's what asks the "cloud" to provision a LoadBalancer.

### Worker nodes (the "muscle")
- **kubelet** — agent on each node. Talks to the API server, starts/stops containers
  via the container runtime, reports status.
- **kube-proxy** — programs iptables/IPVS rules on the node so Services route traffic
  to the right Pods.
- **container runtime** — actually runs containers. In kind it's `containerd` inside
  the kind node container. On a real Linux box it might be `containerd` or `CRI-O`.

### How kind fits
kind runs the **entire cluster** (control plane + worker) inside a single Docker
container called `kind-control-plane`. Inside that container: etcd, API server,
kubelet, containerd, kube-proxy — all running as processes. That's why you can
"delete the cluster" with one command: `kind delete cluster` just removes the Docker
container. Our cluster is single-node, so the control plane and worker role are
on the same node.

```
   your Mac
   └── Docker
       └── container: kind-control-plane
           ├── etcd
           ├── kube-apiserver
           ├── kube-controller-manager
           ├── kube-scheduler
           ├── kubelet
           ├── kube-proxy
           └── containerd ── runs your app pods (also as nested containers)
```

---

## 4. The API server is the only way in

Every actor in the system (you, controllers, kubelets, other pods) talks to the same
endpoint: the **API server**, over HTTPS. Nothing reads etcd directly except the API
server. This means:

- `kubectl get pods` → API server → etcd → back.
- A controller creating a Pod → API server → etcd → scheduler sees it → kubelet on a
  node gets told → containerd starts the container.
- `kubectl apply -f foo.yaml` → just sends YAML to the API server; controllers do the rest.

`kubectl` is basically a fancy HTTP client. You could `curl` the API server directly
(with a client cert) and get the same result. This is why `kubectl config use-context`
matters — it picks which API server + credentials to use.

---

## 5. Core resource types you'll meet

These are the "nouns" of k8s. Every stage introduces new ones; here's the foundation:

| Resource        | What it is                                            | Manages                  |
|-----------------|-------------------------------------------------------|--------------------------|
| **Pod**         | 1+ containers, shared network, co-located             | the actual workload      |
| **ReplicaSet**  | "Always keep N copies of this Pod running"            | Pods                     |
| **Deployment**  | "Roll out version X of this ReplicaSet, roll updates" | ReplicaSets              |
| **Service**     | stable DNS name + IP that routes to a set of Pods     | Pods (via selectors)     |
| **Ingress**     | HTTP(L7) routing from outside the cluster to Services | Services                 |
| **ConfigMap**   | config data (non-secret) injected into Pods           | -                        |
| **Secret**      | sensitive data, base64-encoded, injected into Pods    | -                        |
| **Volume/PV/PVC** | persistent storage                                  | -                        |
| **Namespace**   | logical grouping of resources (tenancy)               | all of the above         |

The hierarchy: **Deployment → ReplicaSet → Pod → container**. You almost never create
Pods directly; you create a Deployment and let k8s make the Pods.

---

## 6. Services: how networking works inside the cluster

A Pod's IP changes every time it restarts. So you can't rely on Pod IPs. A **Service**
gives you a **stable IP + DNS name** that load-balances across the matching Pods.

Three Service types you need to know now:

- **ClusterIP** (default) — reachable only *inside* the cluster. Use this for internal
  services (e.g. a database the app talks to).
- **NodePort** — opens a port (30000–32767) on **every node's** IP. Reachable from
  outside the cluster but on a high port. Building block for LoadBalancer.
- **LoadBalancer** — asks the cloud provider (or cloud-provider-kind) to provision a
  real load balancer pointing at the Service. External IP gets assigned. This is the
  production-grade way to expose a service.

### Ingress vs LoadBalancer Service
Both expose your app outside the cluster, but at different OSI layers:

- **LoadBalancer Service** — L4 (TCP). One Service = one external IP = one port. Want
  10 services? Get 10 IPs. Expensive.
- **Ingress** — L7 (HTTP/HTTPS). One external IP can route to many Services based on
  host header (`mlflow.local` → MLflow, `api.local` → API). Needs an Ingress controller
  to actually receive traffic. In our cluster, **cloud-provider-kind** plays the role of
  both Ingress controller *and* LoadBalancer provider.

Rule of thumb: HTTP app → Ingress. TCP/non-HTTP → LoadBalancer Service.

---

## 7. What is cloud-provider-kind and why does it exist?

On a real cloud (AWS/GCP/Azure), when you create a `Service: type: LoadBalancer`,
k8s's cloud-controller-manager calls the cloud API → AWS provisions an ELB → traffic flows.
On a local dev cluster (kind, minikube, k3d) there is no cloud. So historically:

- Old way: install `ingress-nginx`, hack `extraPortMappings` so port 80 on the kind node
  container maps to port 80 on your Mac. Worked but messy.
- New way (kind v0.27+): **cloud-provider-kind** — a tiny "fake cloud" binary that runs
  on your host. It watches for LoadBalancer Services and Ingresses, and creates a
  **Docker container** to act as the load balancer. The container has a Docker bridge
  IP (e.g. `192.168.97.3`) reachable from your Mac, and forwards traffic to the right
  kind node. This is why our Ingress example got the IP `192.168.97.3` — that's a
  Docker container, not a pod.

```
   curl → 192.168.97.3 (LB container) → kind-control-plane container → Service → Pod
```

This mirrors how real clouds work but locally. That's why we run it with `sudo`: it
needs to manage Docker containers and host networking.

---

## 8. The kind-config.yaml — what those fields mean

```yaml
apiVersion: kind.x-k8s.io/v1alpha4
kind: Cluster
name: kind
nodes:
- role: control-plane
  image: kindest/node:v1.36.1
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
```

- `kind: Cluster` — this is a kind-specific config, **not** a k8s manifest. You feed it
  to the `kind` binary, not `kubectl`.
- `nodes[].role: control-plane` — one node, control-plane role (in a multi-node cluster
  you'd add `- role: worker` lines).
- `image: kindest/node:v1.36.1` — the Docker image kind uses as the "node". It bundles
  kubeadm + kubelet + containerd + all the k8s binaries for that version. Pinning it
  pins your k8s version.
- `kubeadmConfigPatches` — raw patches fed to `kubeadm` (the tool that bootstraps a k8s
  cluster inside the node). Here we add a label `ingress-ready=true` to the node — a
  legacy hint some ingress controllers check. cloud-provider-kind doesn't actually need
  it; we keep it for compatibility with older guides.

---

## 9. `kubectl` — the API client

`kubectl` is the official CLI client for the API server. Mental model:

```
kubectl <verb> <resource-type> [name] [flags]
        │      │                │
        │      │                └── which object (optional; if omitted, all)
        │      └── what kind of object (pod, deployment, service, ingress...)
        └── get, apply, delete, describe, logs, exec, port-forward...
```

Common verbs:
- `kubectl get X` — list objects of type X
- `kubectl apply -f file.yaml` — create or update objects from a YAML file
- `kubectl delete -f file.yaml` — remove objects defined in a YAML file
- `kubectl describe pod <name>` — verbose view (events, status, container list)
- `kubectl logs <pod>` — stdout/stderr of the first container
- `kubectl exec -it <pod> -- sh` — get a shell inside a container
- `kubectl port-forward svc/X 8080:80` — tunnel a local port to a Service (debugging)
- `kubectl explain pod.spec` — built-in docs for any field (use this a lot!)

`kubectl explain` is your best friend. Don't memorize YAML fields — look them up:
`kubectl explain deployment.spec.strategy.rollingUpdate`.

---

## 10. Namespaces

A **Namespace** is a logical partition of the cluster. Resources inside one namespace
have unique names *within that namespace* — two namespaces can both have a `nginx`
Deployment without colliding.

- `default` — where your stuff lands if you don't specify.
- `kube-system` — control-plane pods (API server, etcd, coredns, kube-proxy).
- `local-path-storage` — the local-path provisioner (a CSI driver for PVCs).
- `ingress-nginx` (would be) — where the ingress controller lives if you used one.
- Later stages: `mlflow`, `kubeflow`, `argocd`, etc.

Use namespaces to group related resources (e.g. one per app, one per team, one per
environment). You'll see `kubectl -n <namespace>` everywhere — it scopes the command.

---

## 11. The reconcile loop, concretely

You'll see this pattern repeat for every resource. Example: Deployment.

1. You `kubectl apply -f deployment.yaml` → API server stores it in etcd.
2. The **Deployment controller** (in controller-manager) notices a new Deployment.
3. It creates a **ReplicaSet** to manage N replicas of the Pod template.
4. The **ReplicaSet controller** notices the new ReplicaSet.
5. It creates N **Pods** (just Pod objects in etcd — no containers yet).
6. The **scheduler** notices unscheduled Pods, picks a node, writes `nodeName` on the Pod.
7. The **kubelet** on that node notices a Pod assigned to it.
8. kubelet calls containerd to pull images and start containers.
9. kubelet reports Pod status back to the API server.
10. If a container dies → kubelet restarts it (per Pod restartPolicy).
11. If a Pod dies entirely → ReplicaSet controller notices the count dropped → creates a
    new Pod → loop.

No single component "runs the show". Each controller watches a slice of etcd and reacts.
This is why k8s is resilient: there's no single point of failure in the control logic.

---

## 12. What you should be able to explain after stage 00

- Why k8s exists (orchestration, declarative, reconcile loop).
- The control plane components and what each does.
- What a Pod / Deployment / Service / Ingress is at a high level.
- The difference between ClusterIP, NodePort, LoadBalancer, Ingress.
- What cloud-provider-kind does and why we need sudo for it.
- Why `kubectl apply` works (API server → etcd → controllers → kubelet → containerd).
- How kind turns a Docker container into a k8s cluster.

If any of these is fuzzy, re-read that section before moving to stage 01. Stage 01 makes
Pods, Deployments, and Services concrete by running them and watching the loop happen.

---

## Further reading (official docs, fetched live)

- Kubernetes architecture: https://kubernetes.io/docs/concepts/overview/components/
- Kubernetes API fundamentals: https://kubernetes.io/docs/concepts/overview/kubernetes-api/
- Declarative vs imperative: https://kubernetes.io/docs/concepts/overview/working-with-objects/kubernetes-objects/
- kind ingress guide: https://kind.sigs.k8s.io/docs/user/ingress/
- cloud-provider-kind: https://github.com/kubernetes-sigs/cloud-provider-kind