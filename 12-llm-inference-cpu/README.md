# 12 — LLM inference on CPU

> Status: scaffolded. Model choice: **Qwen2.5-0.5B** (small enough for Mac CPU).

## Objectives
- Serve Qwen2.5-0.5B via `vllm --device cpu` (fallback: llama.cpp GGUF).
- Expose through Ingress (`llm.local`).
- Add HPA on CPU + custom inference latency metric.
- Benchmark latency/throughput on Mac CPU; record in NOTES.md.

## Try next
`../13-llm-finetune-pipeline/`
