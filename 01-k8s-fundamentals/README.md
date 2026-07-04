# 01 — Kubernetes fundamentals

> Status: scaffolded. Concepts + manifests get filled in when you start this stage.

## Objectives
- Run a Pod imperatively (`kubectl run`) and declaratively (manifest).
- Scale a Deployment and observe ReplicaSet behaviour.
- Expose a Service (ClusterIP, NodePort) and reach it.
- Use Labels / Selectors to filter resources.

## Run (later)
```bash
kubectl apply -f manifests/pod.yaml
kubectl apply -f manifests/deployment.yaml
kubectl apply -f manifests/service.yaml
```

## Try next
`../02-storage-config/`
