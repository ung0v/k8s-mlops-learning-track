# 15 — Capstone: end-to-end MLOps on k8s

> Status: scaffolded.

## Objectives
- Argo CD manages everything: MLflow + serving app + KFP install + a CronJob that triggers a nightly KFP run.
- A git push to this repo triggers Argo CD to sync; a new model version triggers serving pod rollout.
- One command: `make 15-up`.
- Record a 5-minute walkthrough in NOTES.md covering the data path end to end.

## Done
You've built a complete CPU-only MLOps platform on a single-node kind cluster.
