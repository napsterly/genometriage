"""Preregistered deterministic conflict-arbitration policy."""

from __future__ import annotations

from typing import Dict, Sequence

from genometriage.models.phase2 import EvidenceRecord
from genometriage.models.phase3 import ArbitrationRecord


POLICY_VERSION = "conflict_arbitration_v1"
STRENGTH_WEIGHTS: Dict[str, int] = {"weak": 1, "moderate": 2, "strong": 3}
CONTEXTUAL_COUNTER_DIMENSIONS = {
    "phenotype_context",
    "inheritance",
    "population",
    "provenance",
}
RETAINED_STATES = {"retain", "conflicting_evidence"}


def arbitrate_candidate(
    variant_id: str,
    source_rank: int,
    records: Sequence[EvidenceRecord],
) -> ArbitrationRecord:
    """Apply conflict_arbitration_v1 exactly as preregistered."""

    ordered = sorted(records, key=lambda record: record.evidence_id)
    identifiers = [record.evidence_id for record in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate evidence IDs for arbitration: {variant_id}")

    grouped = {
        direction: [
            record for record in ordered if record.content.direction == direction
        ]
        for direction in ("supports", "against", "uncertain")
    }
    scores = {
        direction: sum(STRENGTH_WEIGHTS[record.content.strength] for record in items)
        for direction, items in grouped.items()
    }
    contextual_strong = [
        record
        for record in grouped["against"]
        if record.content.strength == "strong"
        and record.content.dimension in CONTEXTUAL_COUNTER_DIMENSIONS
    ]
    support = scores["supports"]
    counter = scores["against"]
    uncertainty = scores["uncertain"]

    if support == 0 and counter == 0:
        state = "insufficient_evidence"
        fired_rule = "1_insufficient_no_directional_evidence"
    elif support == 0 and counter > 0:
        state = "deprioritize"
        fired_rule = "2_counterevidence_only"
    elif contextual_strong and counter >= support:
        state = "deprioritize"
        fired_rule = "3_contextual_strong_counter"
    elif counter >= support + 2:
        state = "deprioritize"
        fired_rule = "4_aggregate_counter_dominance"
    elif support < 3:
        state = "insufficient_evidence"
        fired_rule = "5_below_support_threshold"
    elif counter > 0 or uncertainty > 0:
        state = "conflicting_evidence"
        fired_rule = "6_material_conflict_or_uncertainty"
    else:
        state = "retain"
        fired_rule = "7_unopposed_support"

    retained = state in RETAINED_STATES
    reason = (
        f"{POLICY_VERSION} fired {fired_rule}: support={support}, "
        f"counter={counter}, uncertainty={uncertainty}; state={state}."
    )
    return ArbitrationRecord(
        variant_id=variant_id,
        source_rank=source_rank,
        state=state,
        support_score=support,
        counter_score=counter,
        uncertainty_score=uncertainty,
        supporting_evidence_ids=[record.evidence_id for record in grouped["supports"]],
        counterevidence_ids=[record.evidence_id for record in grouped["against"]],
        uncertainty_evidence_ids=[record.evidence_id for record in grouped["uncertain"]],
        contextual_strong_counter_ids=[
            record.evidence_id for record in contextual_strong
        ],
        fired_rule=fired_rule,
        retained_for_review=retained,
        reason=reason,
    )
