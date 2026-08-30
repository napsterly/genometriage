# Representative agent trajectories

**For research/expert review. Not a medical diagnosis.**

These trajectories are generated exclusively from retained benchmark cases,
frozen evidence stores, raw structured predictions, and evaluator outputs. They do
not expose or invent private chain-of-thought. “Model input summary” means an
artifact-backed description of the recorded input boundary—not hidden reasoning.

Regenerate them without an API call:

```powershell
.\.venv\Scripts\python.exe scripts\build_trajectories.py
```

## Selected trajectories

| File | Track | Why it is representative |
|---|---|---|
| `01_straightforward_gt001.json` | Frozen synthetic | Straightforward V1 success with one supported shortlisted candidate and no uncertainty escalation. |
| `02_noisy_gt002.json` | Frozen synthetic | V0 returned three review candidates; the complete V1 pipeline retained one and removed two. |
| `03_conflict_gc003.json` | Held-out conflict | V1 retained two plausible candidates and explicitly escalated uncertainty; the file also preserves the experimental V3 follow-up. |
| `04_public_gp009.json` | Public ClinVar proxy | A real public PAH locus backed by a pinned expert-panel aggregate record and exact source/version provenance. |
| `05_v3_regression_gt004.json` | Frozen regression | The decisive V3 failure: the frozen arbitration threshold removes both relevant V1 candidates, explaining why V3 is not the global default. |

Each JSON file includes:

- model-visible case input;
- exact system, prompt version/hash, model, usage, and recorded timestamp;
- deterministic normalized variants;
- the frozen evidence records actually retrieved, including provenance;
- a bounded model-input summary;
- the actual structured model response;
- resulting shortlist and human-review checkpoint;
- evaluator metrics clearly marked as evaluation feedback;
- retained retry/failure records, including an empty list when no retry occurred;
- optional V0 or V3 comparison where relevant;
- the mandatory safety statement.

Ground-truth variant identifiers are not copied into these trajectory artifacts.
The explicit evaluator section contains outcome metrics only. Evaluator-only labels
remain in their sealed benchmark files.
