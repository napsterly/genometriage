# Improvement changelog

| Stage | What we tried & why | Evidence | Decision / Learning |
|---|---|---|---|
| Baseline | Single general-purpose model evaluates each case | `results/baseline-gemini.json` (2026-08-29): 12/12 evaluated; Recall@5 1.000; Precision@5 0.233; MRR 1.000; 9 false positives@5; 23 variants sent for review; unsupported-claim proxy 0.000; estimated free-tier API cost $0.00 | Establish the Phase 1 comparison point; retain raw predictions and exact execution settings |

Do not add an iteration here until it has been run on the same sealed benchmark and its result artifact is available.

Run note (2026-08-29): the live API compatibility check reached the provider after removing an unsupported JSON Schema keyword, but the account returned `insufficient_quota`. No valid benchmark result was produced, and failed-run zero placeholders were not retained as metrics.

Provider note (2026-08-29): Gemini became the default execution provider so the unchanged one-call baseline can use Google's free tier. The initial compatibility request showed that `gemini-2.5-flash` is unavailable to new users, so the pinned model was changed to Google's directed replacement, `gemini-3.6-flash`. OpenAI remains selectable for like-for-like provider comparisons. This is not a new system iteration, and no benchmark metrics are recorded until a successful sealed run completes.

Compatibility note (2026-08-29): a pre-result Gemini run returned truncated JSON on case 8 because the original 2,000-token response ceiling also covered model thinking. The run used fail-fast and no partial metric artifact was written. Gemini thinking is now pinned to `low` and the response ceiling is 8,192 tokens; these are execution-compatibility settings for the same baseline, not a new iteration.

Quota note (2026-08-29): the free-tier API reported a five-request limit for `gemini-3.6-flash`. A pre-result run stopped on HTTP 429 without writing partial metrics. Gemini runs now use a deterministic 13-second minimum request-start interval by default, preserving one call per case while staying below that observed limit.

Completed run note (2026-08-29): the `gemini-3.6-flash` project bucket was exhausted during compatibility work, so the clean benchmark was run from a fresh checkpoint with the stable, structured-output-capable free-tier `gemini-3.1-flash-lite`. All 12 cases completed under one fixed configuration. This exact model is now the default so the retained prediction and result artifacts match the documented reproduction command.
