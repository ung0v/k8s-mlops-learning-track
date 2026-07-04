# 00 — Bootstrap: cluster baseline used by every stage

One-time setup so later stages can assume a working kind cluster with ingress and a few convenience helpers.

## Objectives

- Confirm the kind cluster is healthy.
- Install ingress-nginx (used by stages 05, 09, 12, 15 for HTTP access instead of `port-forward`).
- Pin a couple of helper aliases / scripts used across stages.

## 1. Verify cluster

```bash
kubectl get nodes
kubectl get pods -A
```

You should see `kind-control-plane` Ready and coredns / local-path-provisioner running in `kube-system`.

## 2. Install ingress-nginx

kind needs a specific ingress-nginx config to work with its port-mapped control-plane. Apply the manifest here:

```bash
kubectl apply -f manifests/ingress-nginx.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

Verify the controller is up:

```bash
kubectl get pods -n ingress-nginx
```

### Reaching ingress from the host

kind maps ports 80/443 of the control-plane container to the host. To confirm:

```bash
docker port kind-control-plane
```

You should see `80/tcp -> 0.0.0.0:80` (and 443). If not, see the Troubleshooting section — your cluster was created without port mappings and you'll need to recreate it with the bootstrap config in `manifests/kind-config.yaml`.

## 3. (Optional) Recreate cluster with the bootstrap config

Only if `docker port kind-control-plane` did **not** show 80/443 mappings:

```bash
kind delete cluster
kind create cluster --config manifests/kind-config.yaml
kubectl apply -f manifests/ingress-nginx.yaml
```

The bootstrap config bumps the node memory to 8 GiB and explicitly maps 80/443/8080 to the host. The larger memory budget matters once we install Kubeflow Pipelines in stage 07.

## 4. Convenience aliases (optional, recommended)

Add to your shell:

```bash
alias k=kubectl
alias kgp='kubectl get pods -A'
alias kgs='kubectl get svc -A'
alias kdesc='kubectl describe'
alias kl='kubectl logs -f'
```

## 5. What "done" looks like

- `kubectl get nodes` → 1 Ready node
- `kubectl get pods -n ingress-nginx` → controller Ready
- `curl http://localhost` from the host → 404 from nginx (expected: no Ingress objects yet)

## Try next

`../01-k8s-fundamentals/` — Pod, Deployment, Service basics, validated against this bootstrapped cluster.

## Troubleshooting

- **No port mapping on the control-plane:** cluster was created without `extraPortMappings`. Recreate with `manifests/kind-config.yaml`.
- **ingress-nginx pending:** check events with `kubectl describe pod -n ingress-nginx <pod>`; usually a missing port mapping, not a resource issue.
- **Mac DNS for ingress hostnames:** add entries to `/etc/hosts` (e.g. `127.0.0.1 mlflow.local`) when stages use named Ingress hosts.