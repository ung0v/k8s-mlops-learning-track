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