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

## Stage 02 — Storage & config

- kind's default StorageClass is named **`standard`** (provisioner `rancher.io/local-path`), NOT `local-path`. Omit `storageClassName` in PVCs to use the default — safest and portable.
- `standard` uses `WaitForFirstConsumer` binding mode: the PVC stays Pending until a Pod actually schedules and requests it. This is normal, not a bug.
- Single-Pod LoadBalancer Services on single-node kind can be flaky via cloud-provider-kind (TCP connects, HTTP times out). Works fine with multiple replicas (e.g. StatefulSet). For single-Pod demos, prefer `kubectl port-forward pod/<name> <local>:<remote>`.
- Headless Service (`clusterIP: None`) + StatefulSet gives each Pod a stable DNS name: `web-0.web-svc.default.svc.cluster.local`. Only resolvable from inside the cluster (use a debug Pod).
- StatefulSet Pods are created sequentially (web-0 → web-1 → web-2) and deleted in reverse. PVCs are retained on scale-down (not deleted), so scaling back up reattaches the same data.
- Init containers run to completion before the main container starts. Status shows as `Init:0/1` (0 of 1 init containers completed).

## Stage 05 — Serving + HPA

- metrics-server manifest needs: (1) no `--kubelet-use-node-status` flag (not valid in v0.7.2), (2) `list,watch` on configmaps (not just `get`), (3) an `APIService` resource (`v1beta1.metrics.k8s.io`) pointing to the metrics-server Service. Without the APIService, `kubectl top` returns "Metrics API not available" even though the pod is Running.
- `kubectl top nodes` takes ~30-60s after metrics-server starts before it returns data.
- HPA shows `cpu: <unknown>/70%` until metrics-server is fully registered; then shows real CPU%.
- Serving Pod with `readOnly: true` PVC mount + `runAsUser: 1000` works on kind's local-path StorageClass (dir is mode 0777).
- Ingress with `host: serve.local` works via cloud-provider-kind — add the Ingress IP to `/etc/hosts` to curl by name, or use `-H "Host: serve.local"` with the IP directly.

## Stage 04 — Jobs

- Job `restartPolicy` must be `OnFailure` or `Never` (not `Always` — that's for Deployments).
- `kubectl wait --for=condition=Complete job/<name>` is the right way to wait for a Job.
- CronJob `*/2 * * * *` schedules at even minute boundaries (00, 02, 04...), not "2 minutes after apply". First scheduled run can take up to 2 min.
- `concurrencyPolicy: Forbid` prevents overlapping Jobs — important for training (prevents two Jobs writing to the same model file).
- Job Pod shows `STATUS: Completed` (not `Running`) — this is the key visual difference from a Deployment Pod.

## Stage 06 — GitOps / Argo CD

- Argo CD install manifest is huge (~33k lines). Download it first with `curl` to avoid GitHub rate limits on `raw.githubusercontent.com`.
- The ApplicationSet CRD may show "metadata.annotations: Too long" — this is a cosmetic warning; the install still succeeds.
- Argo CD installs NetworkPolicies that can block pod-to-pod traffic on kind's simple CNI (kindnet). If `argocd-application-controller` can't reach `argocd-redis` (DNS timeout), delete the NetworkPolicies: `kubectl delete networkpolicy -n argocd --all`. Then restart the application controller: `kubectl delete pod -n argocd argocd-application-controller-0`.
- `file://` repoURL doesn't work on kind — the repo-server Pod is inside the kind container and can't see your Mac's filesystem. Use a public GitHub repo (e.g. `argoproj/argocd-example-apps`) or push your repo to GitHub.
- `spec.project: default` is required on the Application manifest (or the API rejects it).
- Self-heal runs on ~30s intervals. `kubectl scale` → Argo CD detects drift → reverts within 30s.

## Stage 07 — KFP (planned, not yet verified live)

- KFP v2 latest is `2.16.1`. Install via kustomize: `kubectl apply -k "github.com/kubeflow/pipelines/manifests/kustomize/env/dev?ref=2.16.1"`.
- UI via port-forward: `kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80`.
- KFP needs ~4 GiB RAM. If kind node is OOM-killed, increase Docker Desktop memory to 8 GiB.
- KFP uses Argo Workflows under the hood — the `workflow-controller` pod in `kubeflow` namespace is the same binary as stage 08's.

## Stage 08 — Argo Workflows (planned, not yet verified live)

- Argo Workflows `quick-start-minimal.yaml` is truly minimal — only 2 pods (argo-server + workflow-controller). Much lighter than KFP.
- UI on port 2746 (https, not http) — accept the self-signed cert.
- Install: `kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.6.4/quick-start-minimal.yaml`.