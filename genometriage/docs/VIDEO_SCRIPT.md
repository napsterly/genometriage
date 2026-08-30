# GenomeTriage video demo script

Target duration: **4:40**. Hard maximum: **5:00**.

Use Judge Mode entirely offline. Keep the “Recorded benchmark execution /
deterministic replay” label visible. Do not depend on Gemini availability while
recording.

## 0:00–0:30 — Problem

**Visual:** README headline, then Judge Mode hero.

**Narration:**

“Genomic analysis can produce many candidate variants. Researchers and expert
reviewers need to decide which variants deserve attention without wasting review
time. GenomeTriage turns a noisy candidate set into a smaller, evidence-backed
shortlist. It is research decision support—not a diagnostic system.”

## 0:30–0:55 — Baseline

**Visual:** Open **V0 vs V1** for `GT-002`. Point to the three V0 candidates.

**Narration:**

“Our deliberately simple baseline makes one general-purpose Gemini call. Across
the frozen benchmark it found all relevant variants in the top three, but returned
nine false positives and sent 23 variants for review.”

## 0:55–2:10 — GenomeTriage V1

**Visual:** Return to **Triage** with `GT-002`. Move through the workflow strip,
normalized variants, evidence snapshot, shortlisted variant, evidence IDs, and the
human-review checkpoint. Expand one technical-details panel.

**Narration:**

“V1 is the retained product workflow. Ordinary code normalizes the alleles. Exact
matching retrieves evidence from a frozen local store. One evidence-constrained
model call ranks a maximum of three candidates and cites evidence IDs. Here, V1
retains one candidate and removes two noisy baseline review items. A reviewer can
see the normalized representation, evidence strength and category, provenance,
counterevidence, uncertainty, exact prompt/model version, and token usage. The
result still stops at a qualified human review checkpoint.”

“This screen is a recorded benchmark execution and deterministic replay. No live
API call is being presented as new.”

## 2:10–2:50 — Measured improvement

**Visual:** Open **Evaluation** and show the four headline cards and top-3 control.

**Narration:**

“On the frozen benchmark, the complete V1 evidence-grounded pipeline reduced false
positives from nine to two—a 77.8 percent reduction. Review burden fell from 23 to
16, or 30.4 percent. Recall at three stayed at 100 percent, and shortlist precision
rose from 60.9 to 87.5 percent.”

“The deterministic V0-top3 control was prediction-identical to V0. Truncation
explained zero of the seven false-positive reductions. We attribute the result to
the complete V1 pipeline—not retrieval alone.”

## 2:50–3:30 — Generalization

**Visual:** Stay on Evaluation. Point to held-out conflict and public cards; then
select public case `GP-009` in Triage and show source provenance.

**Narration:**

“On 13 unseen conflict-heavy cases, V1 preserved Recall at three, with four false
positives. Experimental deterministic V3 arbitration removed all four on that
track without adding a model call.”

“On a frozen 10-case benchmark built from real public ClinVar records, V1 achieved
Recall at three of 1.000 and shortlist precision of .909. The loci and versioned
records are real and evaluation has no live database dependency. But labels are a
deterministic ClinVar-metadata proxy—not independently adjudicated clinical truth.”

## 3:30–4:05 — What did not work

**Visual:** Open **Journey**. Highlight V2 and V3.

**Narration:**

“We did not promote complexity just because it looked agentic. V2 added an
independent model verifier. It increased runtime and tokens but did not improve the
shortlist, so we did not retain it.”

“V3 was excellent on structured conflict and public evidence, but legacy regression
Recall at three fell from 1.000 to .909. It remains experimental instead of silently
replacing V1.”

## 4:05–4:35 — Hot Take

**Visual:** Center the Journey quote.

**Narration:**

“Our project’s hot take is: More agents did not make genomic triage more reliable.
Better evidence structure did. The bottleneck we observed was evidence calibration,
not reasoning capacity. That is a benchmark-specific engineering lesson, not a
universal claim about genomic medicine.”

## 4:35–4:50 — Close

**Visual:** Return to hero, then briefly show Reproduce commands.

**Narration:**

“GenomeTriage is evidence-grounded prioritization, measured against a frozen
baseline, reproducible offline, and explicitly human-reviewed. For research and
expert review—not a medical diagnosis.”

## Recording checklist

- Record at 1440×900 or 1920×1080.
- Start the app before recording and confirm the replay label is visible.
- Use `GT-002` for the primary same-case demonstration.
- Use `GP-009` for public provenance.
- Never paste or display an API key.
- Do not call the replay “live.”
- Keep the final export under five minutes.
