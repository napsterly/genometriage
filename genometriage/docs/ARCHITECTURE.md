# Architecture

Phase 1 intentionally stops at a benchmark, one-call baseline, and evaluator.

```text
model-visible JSONL ──> deterministic Pydantic parsing ──> one LLM call ──> raw SystemRun JSON
                                                        (Gemini default; OpenAI optional)
                                                                          │
sealed ground truth JSONL ─────────────────────────────────────────────────┼──> evaluator ──> result JSON + terminal summary
                                                                          │
versioned prompt + hashes ─────────────────────────────────────────────────┘
```

Ground truth is not a security boundary against a malicious process with repository access. It is a software boundary: systems receive `BenchmarkCase` objects only; the evaluator loads answers after raw predictions have been produced. Later runners must preserve this boundary.

Provider adapters are intentionally thin. Gemini and OpenAI receive the same rendered case, prompt version, and response contract, and each still performs exactly one hosted-model call per case. Runs use `baseline-gemini` or `baseline-openai` as their system identifier to prevent artifacts from silently overwriting or masquerading as one another.

Raw runs are atomically checkpointed after each completed case and marked `in_progress` until all cases finish. Resuming is allowed only when the benchmark hash, prompt hash, model, provider execution settings, and pacing match. The evaluator rejects in-progress checkpoints, preventing quota interruptions from becoming misleading metric files.

`genometriage.interfaces` reserves narrow protocols for normalization, annotation, retrieval, prioritization, independent verification, conflict handling, and reporting. They are deliberately unimplemented. A future system should write the same `SystemRun` contract so evaluation remains comparable.

Deterministic parsing, allele/chromosome normalization, ID checks, metric arithmetic, and report assembly remain outside an LLM. Eventual claims should carry evidence IDs through every stage. Verification failures and evidence conflicts should remain visible and trigger human escalation.
