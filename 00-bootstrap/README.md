# 00 — Bootstrap: cluster baseline used by every stage

One-time setup so later stages can assume a working kind cluster with native Ingress
and a couple of convenience helpers.

> **Architecture (kind v0.32+, July 2026):** kind now supports Ingress and LoadBalancer
> services natively via `cloud-provider-kind` — a standalone host binary that runs
> Docker containers as load balancers. **No ingress-nginx install is needed.**
> This replaces the old `extraPortMappings` + ingress-nginx pattern.

## Objectives

- Install `cloud-provider-kind` (one-time, on the host).
- Recreate the kind cluster with the bootstrap config.
- Start `cloud-provider-kind` so Ingress and LoadBalancer services work.
- Verify with a sample Ingress object.
- Add a few shell aliases.

## 1. Install cloud-provider-kind (one-time)

```bash
go install sigs.k8s.io/cloud-provider-kind@v0.11.1
```

Binary lands at `$(go env GOPATH)/bin/cloud-provider-kind`.

## 2. Recreate the cluster with the bootstrap config

```bash
kind delete cluster
kind create cluster --config manifests/kind-config.yaml --wait 60s
kubectl get nodes
```

You should see `kind-control-plane` Ready. The config is a single control-plane node
on `kindest/node:v1.36.1` with the `ingress-ready=true` node label (kept for compatibility
with older guides — cloud-provider-kind does not actually require it).

> Later (stage 07, KFP) we may bump node memory by switching to a different config;
> that config lives in `07-kubeflow-pipelines/manifests/`. Don't pre-emptively add
> memory limits here — the current config is the cleanest baseline.

## 3. Start cloud-provider-kind (every session)

`cloud-provider-kind` is a host process, not a pod. It must run with `sudo` because it
opens host ports for the LB containers. Open a **dedicated terminal** and run:

```bash
sudo "$(go env GOPATH)/bin/cloud-provider-kind" --enable-default-ingress=true
```

Leave that terminal open while you work on the cluster. You should see log lines like:

```
I0704 ... app.go:90] FLAG: --enable-default-ingress="true"
... starting controller
```

If you see `Error: please run this again with sudo`, you forgot `sudo`.

> **Gotcha:** If you reboot your Mac or close that terminal, Ingress/LB services will
> stop getting external IPs. Just restart the binary. The cluster itself is unaffected.

## 4. Verify native Ingress works

Apply the official kind ingress example (two http-echo pods + an Ingress):

```bash
kubectl apply -f https://kind.sigs.k8s.io/examples/ingress/usage.yaml
```

Wait for the Ingress to get an ADDRESS (cloud-provider-kind assigns it):

```bash
kubectl get ingress
# NAME              CLASS     HOSTS         ADDRESS        PORTS   AGE
# example-ingress   <none>    example.com   172.18.0.N     80      10m
```

Curl it (the ADDRESS is a Docker bridge IP reachable from your Mac):

```bash
INGRESS_IP=$(kubectl get ingress example-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl -H "Host: example.com" http://${INGRESS_IP}/foo   # -> "foo-app"
curl -H "Host: example.com" http://${INGRESS_IP}/bar   # -> "bar-app"
```

If those return the pod hostnames, native Ingress is working. Clean up:

```bash
kubectl delete -f https://kind.sigs.k8s.io/examples/ingress/usage.yaml
```

## 5. Verify LoadBalancer services work

```bash
kubectl apply -f https://kind.sigs.k8s.io/examples/loadbalancer/usage.yaml
LB_IP=$(kubectl get svc/foo-service -o=jsonpath='{.status.loadBalancer.ingress[0].ip}')
curl ${LB_IP}:5678   # -> "foo-app" or "bar-app" (round robin)
kubectl delete -f https://kind.sigs.k8s.io/examples/loadbalancer/usage.yaml
```

## 6. Convenience aliases (optional, recommended)

Add to your `~/.zshrc`:

```bash
alias k=kubectl
alias kgp='kubectl get pods -A'
alias kgs='kubectl get svc -A'
alias kgi='kubectl get ingress -A'
alias kdesc='kubectl describe'
alias kl='kubectl logs -f'
```

## 7. What "done" looks like

- `kubectl get nodes` → 1 Ready node (`kind-control-plane`)
- `cloud-provider-kind` running in a terminal (with sudo)
- `kubectl get ingress` shows an ADDRESS (not `<pending>`) after applying an Ingress
- `curl` of the Ingress IP returns the expected pod response

## Try next

`../01-k8s-fundamentals/` — Pod, Deployment, Service basics, validated against this
bootstrapped cluster. From now on you can use real Ingress objects (not just port-forward)
to reach apps.

## Troubleshooting

- **`Error: please run this again with sudo`** — cloud-provider-kind needs root for host port binding.
- **Ingress ADDRESS stuck on `<pending>`** — cloud-provider-kind is not running. Check the dedicated terminal.
- **LoadBalancer service `<pending>`** — same cause; restart the binary.
- **`curl` to the ingress IP times out** — the Docker bridge IP changes between cluster recreations. Re-fetch it with `kubectl get ingress`.
- **Mac DNS for named Ingress hosts** — add entries to `/etc/hosts` (e.g. `172.18.0.N mlflow.local`). The IP is the one shown by `kubectl get ingress`. For stages that use named hosts (09, 12, 15), I'll show you how.
- **Old nginx test pods from the previous cluster are gone** — that's expected; we deleted the 12-day-old cluster.