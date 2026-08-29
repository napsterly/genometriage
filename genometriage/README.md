# GenomeTriage

GenomeTriage is a benchmark-first research prototype for reducing synthetic genomic
candidate sets to small, evidence-backed shortlists for qualified human review.

**For research/expert review. Not a medical diagnosis.** The project makes no
autonomous diagnosis, treatment recommendation, or clinical decision. All bundled
case data, loci, genes, evidence, and labels are synthetic.

## Phase 2 result

Phase 1's Gemini V0 artifacts are frozen and hash-guarded. Phase 2 tested whether
local evidence retrieval and independent claim verification could preserve V0
Recall@3 while reducing expert-review burden.

| Metric | V0 | V0-top3 | V1 evidence grounded | V2 verified |
|---|---:|---:|---:|---:|
| Recall@3 | 1.000 | 1.000 | 1.000 | 1.000 |
| False positives | 9 | 9 | 2 | 2 |
| Review burden | 23 | 23 | 16 | 16 |
| Review burden at full recall | 14 | 14 | 14 | 14 |
| Shortlist precision | 0.608696 | 0.608696 | 0.875000 | 0.875000 |
| Mean runtime (seconds/case) | 2.321 | 2.321 | 2.522 | 5.601 |
| Total tokens | 23,275 | 23,275 | 42,826 | 69,517 |

V0 already returned at most three candidates per case, so the deterministic top-3
control is prediction-identical to V0: truncation explains none of the seven
false-positive reductions. V1 retains a measurable advantage after that control,
but it is attributed to the complete V1 pipeline comparison rather than retrieval
alone because model, prompt, and selection behavior also changed. V2 preserved
recall and semantic claim support, but did not improve the shortlist beyond V1. See
[`results/phase2-comparison.md`](results/phase2-comparison.md) and the machine-readable
failure analysis in `results/phase2-failure-analysis.json`.

Precision@5 remains 0.233 for all systems because the historical metric uses a fixed
denominator of five even when a system returns fewer than five variants. Review
burden and false-positive count directly capture the reduction.

## Systems

- **V0, frozen:** one general-purpose Gemini call receives the model-visible case.
- **V1:** deterministic allele normalization, exact retrieval from the frozen local
  evidence snapshot, then one evidence-constrained prioritization call. It returns
  at most three candidates.
- **V2:** reuses V1 output and makes one independent verification call for each case
  with claims. It cannot introduce or reorder candidates. Deterministic report
  assembly prevents contradicted or insufficient claims from appearing as
  established facts.

Ground truth is loaded only by evaluation after raw predictions exist. V1/V2 never
receive the evaluator-only files.

## Clean installation

Python 3.10 or newer is required. Runtime, build, and test dependencies are pinned
in `pyproject.toml`.

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
.\.venv\Scripts\python.exe -m genometriage.evidence.build
.\.venv\Scripts\python.exe -m pytest -q
```

macOS/Linux:

```bash
./.venv/bin/python -m genometriage.benchmark.validate
./.venv/bin/python -m genometriage.evidence.build
./.venv/bin/python -m pytest -q
```

The evidence build must report 53 records. Its hash is pinned in
`data/evidence/evidence_v1_manifest.json`.

## Configure Gemini for a new live run

Copy `.env.example` to the ignored `.env` and add a Gemini API key. Never place a
key in source, shell history, predictions, results, or chat.

Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and set GEMINI_API_KEY; do not paste it into this command history.
```

macOS/Linux:

```bash
test -f .env || cp .env.example .env
# Edit .env and set GEMINI_API_KEY; do not paste it into shell history.
```

The retained runs used the standard Gemini free tier and explicit zero rates. Set
both cost variables to `0` only when AI Studio confirms that the key's project is
on that tier. Otherwise supply the applicable current prices or leave them blank,
which produces `null` rather than an invented cost.

## Run V1 and V2 live

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m genometriage.phase2.run --system v1 --provider gemini --model gemini-3.5-flash-lite --fail-fast --resume
.\.venv\Scripts\python.exe -m eval.run --system v1 --predictions predictions/evidence-grounded-v1.json --output results/evidence-grounded-v1.json

.\.venv\Scripts\python.exe -m genometriage.phase2.run --system v2 --provider gemini --model gemini-3.5-flash --v1-predictions predictions/evidence-grounded-v1.json --fail-fast --resume
.\.venv\Scripts\python.exe -m eval.run --system v2 --predictions predictions/verified-v2.json --output results/verified-v2.json

.\.venv\Scripts\python.exe -m genometriage.reporting.comparison
```

macOS/Linux:

```bash
./.venv/bin/python -m genometriage.phase2.run --system v1 --provider gemini --model gemini-3.5-flash-lite --fail-fast --resume
./.venv/bin/python -m eval.run --system v1 --predictions predictions/evidence-grounded-v1.json --output results/evidence-grounded-v1.json

./.venv/bin/python -m genometriage.phase2.run --system v2 --provider gemini --model gemini-3.5-flash --v1-predictions predictions/evidence-grounded-v1.json --fail-fast --resume
./.venv/bin/python -m eval.run --system v2 --predictions predictions/verified-v2.json --output results/verified-v2.json

./.venv/bin/python -m genometriage.reporting.comparison
```

Each live run is atomically checkpointed after every completed case. `--resume`
accepts a checkpoint only when benchmark, prompt, model, evidence, and execution
settings match exactly. V2 reads retained V1 predictions and does not rerun V1.

## Reproduce retained results without API calls

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.run --system baseline --predictions predictions/baseline-gemini.json --output results/baseline-gemini-phase2-replay.json
.\.venv\Scripts\python.exe -m genometriage.controls.v0_top3
.\.venv\Scripts\python.exe -m eval.run --system v0-top3-control --predictions predictions/v0-top3-control.json --output results/v0-top3-control.json
.\.venv\Scripts\python.exe -m eval.run --system v1 --predictions predictions/evidence-grounded-v1.json --output results/evidence-grounded-v1.json
.\.venv\Scripts\python.exe -m eval.run --system v2 --predictions predictions/verified-v2.json --output results/verified-v2.json
.\.venv\Scripts\python.exe -m genometriage.reporting.comparison
```

The test suite verifies every Phase 1 frozen-artifact hash from
`docs/PHASE1_FREEZE.json`. Evaluation replay is deterministic except for result
generation timestamps.

## Phase 1 baseline command

The original one-call baseline remains available but should not overwrite the
frozen retained files during comparison work:

```powershell
.\.venv\Scripts\python.exe -m genometriage.baseline.run --provider gemini --output predictions/baseline-new-run.json
.\.venv\Scripts\python.exe -m eval.run --system baseline --predictions predictions/baseline-new-run.json --output results/baseline-new-run.json
```

## Layout

```text
data/cases/                    model-visible synthetic cases
data/ground_truth/             evaluator-only labels
data/evidence/                 frozen provenance-rich evidence snapshot
data/vcf/                      small supported-subset fixture
prompts/                       versioned V0, V1, and V2 prompts
src/genometriage/normalization/ deterministic VCF-subset normalization
src/genometriage/evidence/     snapshot build, validation, exact retrieval
src/genometriage/phase2/       V1 prioritizer and V2 verifier
src/genometriage/controls/     deterministic no-model benchmark controls
src/genometriage/evaluation/   metrics and sealed-label evaluation
src/genometriage/reporting/    terminal, comparison, failure analysis
tests/                         schema, separation, metrics, and pipeline tests
```

Design details are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/EVIDENCE_STORE.md`](docs/EVIDENCE_STORE.md),
[`docs/METRICS.md`](docs/METRICS.md), and
[`docs/IMPROVEMENT_CHANGELOG.md`](docs/IMPROVEMENT_CHANGELOG.md).
