# Running Notes

Personal scratchpad for gotchas, command snippets, and observations across stages.
Append-only; date each entry.

## Cluster

- Runtime: kind single-node, CPU-only Mac.
- Context: `kind-kind`. Switch with `kubectl config use-context kind-kind`.
- Existing cluster name: `kind-control-plane`.

## Common commands

```bash
# Load a local image into kind (skip a registry)
kind load docker-image <image>:<tag>

# Port-forward a service to localhost
kubectl port-forward svc/<name> <local>:<remote>

# Watch resources
kubectl get pods -A -w
kubectl describe pod <name>
kubectl logs -f <pod>

# Quick temp pod with shell
kubectl run debug --rm -it --image=busybox -- sh
```

## Per-stage log

(empty — fill as you go)

## Stage 00 — Bootstrap

- kind v0.32 supports Ingress natively via `cloud-provider-kind` (no ingress-nginx needed).
- `cloud-provider-kind` is a **host binary** (not a pod); install with `go install sigs.k8s.io/cloud-provider-kind@v0.11.1`.
- It must run with `sudo` (it opens host ports for LB containers). Run it in a dedicated terminal:
  `sudo "$(go env GOPATH)/bin/cloud-provider-kind" --enable-default-ingress=true`
- With cloud-provider-kind, Services of `type: LoadBalancer` and standard `Ingress` objects both work — kind spins up Docker containers that act as load balancers, assigns them an external IP, and routes host ports to them.
- No `extraPortMappings` needed in kind-config.yaml anymore.
- Cluster recreated 2026-07-04 with `00-bootstrap/manifests/kind-config.yaml` (single control-plane, `ingress-ready=true` label kept for compatibility with older guides).