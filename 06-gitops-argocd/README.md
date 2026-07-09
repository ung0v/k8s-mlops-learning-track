# 06 — Lab: GitOps with Argo CD

> Read `concepts.md` first. This lab installs Argo CD and uses it to declaratively manage an
> app from a public git repo (Argo CD's example "guestbook" app).

---

## Objectives

1. Install Argo CD on kind.
2. Access the Argo CD UI.
3. Create an Application that deploys the "guestbook" example from Argo CD's public repo.
4. Watch Argo CD sync the app.
5. Make a manual change (`kubectl scale`) and watch Argo CD self-heal it back.
6. Clean up.

> **Why a public repo instead of this local repo?** Argo CD's repo-server runs inside a Pod
> (inside the kind container), so it can't read `file:///Users/bovn/...`. For a real GitOps
> setup you'd push this repo to GitHub and point Argo CD at that URL. For the lab, we use
> Argo CD's official example repo (`argoproj/argocd-example-apps`, path `guestbook`) — a
> simple Deployment + Service that demonstrates the full GitOps loop.

---

## 0. Prerequisites

- kind cluster running.
- `cloud-provider-kind` running (for Ingress, not strictly needed for this stage).

---

## 1. Install Argo CD

```bash
kubectl create namespace argocd
```

The install manifest is large (~33k lines). Download it first to avoid rate limits:

```bash
curl -sL -o /tmp/argocd-install.yaml https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -n argocd -f /tmp/argocd-install.yaml
kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s
```

Verify all Argo CD pods are running:

```bash
kubectl get pods -n argocd
```

Expected (~7 pods):

```
NAME                                 READY   STATUS    RESTARTS   AGE
argocd-application-controller-0      1/1     Running   0          2m
argocd-applicationset-controller-x  1/1     Running   0          2m
argocd-dex-server-x                  1/1     Running   0          2m
argocd-notifications-controller-x   1/1     Running   0          2m
argocd-redis-x                      1/1     Running   0          2m
argocd-repo-server-x                1/1     Running   0          2m
argocd-server-x                      1/1     Running   0          2m
```

### Get the admin password

```bash
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 --decode
echo
```

Copy this password — you'll use it to log in.

---

## 2. Access the Argo CD UI

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Open **https://localhost:8080** in your browser (accept the self-signed cert). Log in with:
- Username: `admin`
- Password: the one from the previous step

You'll see the Argo CD dashboard with no applications yet.

---

## 3. Install the Argo CD CLI (optional)

```bash
brew install argocd
```

Log in via CLI:

```bash
argocd login localhost:8080 --username admin --password <paste-password> --insecure
```

---

## 4. Create the Application

The manifest in `manifests/application.yaml` points at Argo CD's example repo:

- **repoURL**: `https://github.com/argoproj/argocd-example-apps.git`
- **path**: `guestbook` (a simple Deployment + Service for a guestbook app)
- **syncPolicy.automated**: auto-sync with prune + self-heal

Apply it:

```bash
kubectl apply -f manifests/application.yaml
```

Verify:

```bash
kubectl get application -n argocd
```

Expected:

```
NAME        SYNC STATUS   HEALTH STATUS
guestbook   Synced        Healthy
```

It may take ~30s to go from empty → `OutOfSync` → `Syncing` → `Synced`.

### Watch the sync in the UI

In the Argo CD UI:
1. Click on `guestbook`.
2. You'll see the app topology: Deployment → ReplicaSet → Pods, with a Service attached.
3. The status should show `Synced` and `Healthy` (green).

### Verify the app is running

```bash
kubectl get deployment guestbook-ui
kubectl get pods -l app=guestbook-ui
kubectl get svc guestbook-ui
```

Expected (1 pod running):

```
NAME           READY   UP-TO-DATE   AVAILABLE   AGE
guestbook-ui   1/1     1            1           1m
```

---

## 5. Self-healing: manual drift

Manually scale the Deployment (simulating someone bypassing git):

```bash
kubectl scale deployment/guestbook-ui --replicas=3
kubectl get deployment guestbook-ui
```

For a moment it shows 3 replicas. But Argo CD's `selfHeal: true` detects the drift (git says
1, cluster says 3) and re-applies the git state. Within ~30s:

```bash
kubectl get deployment guestbook-ui
```

Should show `1/1` again. This is the **self-healing** property of GitOps — manual changes
are automatically reverted to match the git source of truth.

> **Note:** Self-heal runs on a ~30s interval. If it doesn't revert immediately, wait and
> re-check. You can also force a sync: `argocd app sync guestbook` (if CLI installed) or
> click "Sync" in the UI.

---

## 6. GitOps in action: make a change in git (optional)

This requires write access to the example repo (you don't have it). To see a git-triggered
sync with your own repo:

1. Fork `argoproj/argocd-example-apps` to your GitHub account.
2. Edit `manifests/application.yaml` → change `repoURL` to your fork.
3. In your fork, edit `guestbook/deployment.yaml` → change `replicas: 1` to `replicas: 4`.
4. Commit and push.
5. Watch Argo CD detect the change and auto-sync to 4 replicas.

For the lab without a fork, the self-healing demo (step 5) is sufficient to demonstrate the
GitOps mechanism.

---

## 7. Clean up

```bash
kubectl delete -f manifests/application.yaml
kubectl delete -f /tmp/argocd-install.yaml
kubectl delete namespace argocd
```

Verify:

```bash
kubectl get pods -n argocd 2>&1
```

Should say "No resources found."

---

## 8. What "done" looks like

- Argo CD UI accessible at https://localhost:8080.
- `guestbook` Application created, `Synced` + `Healthy`.
- `kubectl get deployment guestbook-ui` shows the app deployed by Argo CD.
- `kubectl scale` was self-healed by Argo CD (replicas reverted to match git).
- You can explain: GitOps, Application CRD, sync vs health, self-heal, sync waves.

---

## Try next

`../07-kubeflow-pipelines/` — install Kubeflow Pipelines, author a 3-step pipeline (train →
eval → export), run it, view in the KFP UI. This is the **primary pipeline stage**.

---

## Troubleshooting

- **Install fails with "Too long: may not be more than 262144 bytes"** — this is a cosmetic
  CRD annotation warning; the install still succeeds. Ignore it.
- **Application stays `OutOfSync`** — Argo CD is still pulling. Wait 30s and re-check.
  `argocd app get guestbook` (CLI) or click the app in the UI for details.
- **Application `Unknown` or `Error`** — the repo-server can't reach GitHub. Check
  `kubectl logs -n argocd -l app.kubernetes.io/name=argocd-repo-server`.
- **Self-heal doesn't work** — ensure `selfHeal: true` in the manifest. Check
  `kubectl get application guestbook -n argocd -o yaml | grep selfHeal`.
- **`argocd` CLI not found** — `brew install argocd` or skip the CLI and use the UI + kubectl.