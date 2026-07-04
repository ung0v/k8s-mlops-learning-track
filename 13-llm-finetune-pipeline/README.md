# 13 — LLM fine-tune pipeline

> Status: scaffolded.

## Objectives
- Build a KFP (or Argo) pipeline: download dataset → LoRA PEFT fine-tune (CPU-friendly, Qwen2.5-0.5B) → eval → push to MLflow registry.
- Pipeline writes a new model version; Argo CD notices and rolls the inference pod (stage 12).

## Try next
`../14-monitoring-observability/`
