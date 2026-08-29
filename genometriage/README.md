# GenomeTriage

GenomeTriage Phase 1 is a benchmark-first research prototype for reducing synthetic genomic candidate sets to small, evidence-backed shortlists for qualified human review.

**For research/expert review. Not a medical diagnosis.** This repository does not provide autonomous diagnosis, treatment recommendations, or clinical decisions. All bundled data are synthetic and must not be interpreted as real biological or patient records.

## What Phase 1 contains

- 12 sealed, fully synthetic benchmark cases and evaluator-only labels;
- a deliberately simple `case → one general-purpose LLM call → ranked list` baseline;
- a deterministic evaluation harness with Recall@K, Precision@K, MRR, false positives, an evidence-ID support proxy, shortlist size, runtime, and optional cost;
- validated JSON artifacts, concise terminal reporting, and future-stage protocol boundaries.

No retrieval, multi-agent orchestration, memory, verification loop, or clinical workflow is implemented.

## Clean installation

Python 3.10 or newer is required. Important build, runtime, and test dependencies are exactly pinned in `pyproject.toml`.

Windows PowerShell:

```powershell
cd C:\path\to\genometriage
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==26.1.1
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

macOS/Linux:

```bash
cd /path/to/genometriage
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip==26.1.1
./.venv/bin/python -m pip install -e '.[dev]'
```

## Validate and test

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m genometriage.benchmark.validate
.\.venv\Scripts\python.exe -m pytest
```

macOS/Linux:

```bash
./.venv/bin/python -m genometriage.benchmark.validate
./.venv/bin/python -m pytest
```

## Run the baseline

Gemini is the default provider. The baseline uses one [Gemini `generateContent` request](https://ai.google.dev/api/generate-content) per case, no tools, and structured JSON output. The benchmark-pinned `gemini-3.1-flash-lite` model has free input and output on Google's free tier at the time of writing; availability and rate limits remain controlled by Google. OpenAI remains available as an optional comparison provider.

Copy `.env.example` to the ignored `.env` file, then add the Gemini key obtained from [Google AI Studio](https://ai.google.dev/aistudio). CLI commands load that file automatically without overriding variables already set in the process environment. Never commit or paste a real key into source, logs, chat, or a result artifact.

Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and set GEMINI_API_KEY. Do not paste the key into this command history.
.\.venv\Scripts\python.exe -m genometriage.baseline.run --provider gemini
```

macOS/Linux:

```bash
test -f .env || cp .env.example .env
# Edit .env and set GEMINI_API_KEY. Do not paste the key into shell history.
./.venv/bin/python -m genometriage.baseline.run --provider gemini
```

This writes `predictions/baseline-gemini.json`. Temperature is set to zero, Gemini thinking is pinned to `low`, and case ordering, serialization, schema, and prompt are fixed. Gemini requests start at least 13 seconds apart by default so the 12-case run respects the observed five-request-per-minute free-tier limit; use `--min-request-interval-seconds` only if the active project's published limit differs. Hosted model behavior can still vary. Raw predictions, provider-specific system name, exact model name, prompt/case hashes, timing, and token usage are saved for replay.

To compare the same baseline through OpenAI, set `OPENAI_API_KEY` and run:

```powershell
.\.venv\Scripts\python.exe -m genometriage.baseline.run --provider openai
```

## Run evaluation

Run the baseline and evaluate it in one command:

```powershell
.\.venv\Scripts\python.exe -m eval.run --system baseline
```

This defaults to Gemini, checkpoints each completed case in `predictions/baseline-gemini.json`, writes `results/baseline-gemini.json` only after the run is complete, and prints a concise summary. It exits rather than inventing rankings if credentials are absent. If a quota or network interruption occurs, repeat the command with `--resume`; compatible completed cases are not called again. Add `--provider openai` for the OpenAI comparison path.

```powershell
.\.venv\Scripts\python.exe -m eval.run --system baseline --provider gemini --fail-fast --resume
```

Replay an existing raw run without API calls:

```powershell
.\.venv\Scripts\python.exe -m eval.run --system baseline --predictions predictions/baseline-gemini.json
```

Use explicit pricing only when it matches the selected model and service tier:

```powershell
$env:GENOMETRIAGE_INPUT_COST_PER_MILLION = "<current input price>"
$env:GENOMETRIAGE_OUTPUT_COST_PER_MILLION = "<current output price>"
.\.venv\Scripts\python.exe -m eval.run --system baseline
```

If prices are omitted, cost fields are `null`; no price or metric is fabricated.

If Google AI Studio confirms that the key's project is on the free tier, set both cost rates to `0` to record an estimated API cost of zero rather than `null`. Google's pricing page states that free-tier content may be used to improve its products. This repository contains synthetic data only; do not send private or identifying genomic data through this workflow.

The retained Phase 1 artifact was produced with `gemini-3.1-flash-lite`, 13-second request pacing, low thinking, and zero free-tier cost rates. Its aggregate metrics are evidence from this synthetic benchmark only, not claims of clinical performance.

## Reproduce a result

Given a checked-in commit and a retained raw prediction artifact:

```powershell
git rev-parse HEAD
.\.venv\Scripts\python.exe -m genometriage.benchmark.validate
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m eval.run --system baseline --predictions predictions/baseline-gemini.json --output results/baseline-gemini.json
```

Confirm the benchmark and prompt SHA-256 values in the result and raw run. Evaluation replay is deterministic except for the result generation timestamp. Do not compare a newly sampled model run to an old result without retaining its raw predictions.

## Layout

```text
data/cases/                 model-visible JSONL
data/ground_truth/          evaluator-only labels and rationales
prompts/                    versioned baseline prompt
src/genometriage/baseline/  one-call runner and provider boundary
src/genometriage/benchmark/ fixture loading and integrity checks
src/genometriage/evaluation metrics and result assembly
src/genometriage/interfaces future-stage protocols only
src/genometriage/models/    strict shared schemas
src/genometriage/reporting/ terminal rendering
tests/                      unit and end-to-end harness tests
```

See [benchmark design](docs/BENCHMARK.md), [metric definitions](docs/METRICS.md), [architecture](docs/ARCHITECTURE.md), and the [improvement changelog](docs/IMPROVEMENT_CHANGELOG.md).
