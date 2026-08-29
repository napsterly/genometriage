"""Build and freeze benchmark_conflict_v1 before arbitration is specified."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "data" / "cases" / "benchmark_conflict_v1.jsonl"
TRUTH_PATH = (
    ROOT / "data" / "ground_truth" / "benchmark_conflict_v1_ground_truth.jsonl"
)
MANIFEST_PATH = ROOT / "data" / "manifests" / "benchmark_conflict_v1_freeze.json"
SAFETY = "For research/expert review. Not a medical diagnosis."


def evidence(eid, direction, strength, dimension, statement):
    return {
        "source_id": eid,
        "source_type": "synthetic_benchmark_record",
        "direction": direction,
        "statement": statement,
        "strength": strength,
        "dimension": dimension,
    }


def variant(
    vid,
    chromosome,
    position,
    ref,
    alt,
    gene,
    consequence,
    zygosity,
    inheritance,
    frequency,
    records,
):
    return {
        "variant_id": vid,
        "genome_build": "GRCh38-synthetic",
        "chromosome": chromosome,
        "position": position,
        "reference": ref,
        "alternate": alt,
        "gene": gene,
        "consequence": consequence,
        "zygosity": zygosity,
        "observed_inheritance": inheritance,
        "population_allele_frequency": frequency,
        "evidence": records,
    }


def case(cid, summary, terms, hypothesis, observations, variants):
    return {
        "schema_version": "1.0",
        "case_id": cid,
        "data_origin": "fully_synthetic",
        "safety_disclaimer": SAFETY,
        "context": {
            "summary": summary,
            "phenotype_terms": terms,
            "inheritance_hypothesis": hypothesis,
            "family_observations": observations,
        },
        "candidate_variants": variants,
    }


def truth(cid, relevant, summary, evidence_ids, difficulty, tags):
    rationale = (
        [{"variant_ids": relevant, "summary": summary, "evidence_source_ids": evidence_ids}]
        if relevant
        else []
    )
    return {
        "schema_version": "1.0",
        "case_id": cid,
        "relevant_variant_ids": relevant,
        "rationale": rationale,
        "difficulty": difficulty,
        "challenge_tags": tags,
    }


def build_records():
    cases = []
    truths = []

    cases.append(
        case(
            "GC-001",
            "Synthetic dominant sensory-neuron phenotype with a coding decoy and a noncoding candidate.",
            ["synthetic episodic sensory loss", "synthetic distal pain insensitivity"],
            "de novo dominant",
            ["both synthetic parents unaffected"],
            [
                variant("GC001-V1", "1", 1100101, "A", "G", "CFA1", "missense", "heterozygous", "inherited from unaffected parent", 0.00001, [
                    evidence("GC001-E1", "supports", "strong", "molecular", "A synthetic channel assay shows a marked current reduction for the exact allele."),
                    evidence("GC001-E2", "against", "strong", "phenotype_context", "The invented CFA1 phenotype is isolated night vision loss rather than a sensory-neuron disorder."),
                    evidence("GC001-E3", "against", "moderate", "inheritance", "The allele was inherited from an unaffected synthetic parent under a proposed de novo model."),
                ]),
                variant("GC001-V2", "1", 1100902, "C", "T", "CFB1", "regulatory", "heterozygous", "de novo", 0.000002, [
                    evidence("GC001-E4", "supports", "moderate", "regulatory", "A synthetic enhancer assay shows reduced CFB1 expression for the alternate allele."),
                    evidence("GC001-E5", "supports", "strong", "phenotype_context", "The invented CFB1 phenotype closely matches the sensory-neuron findings."),
                    evidence("GC001-E6", "supports", "strong", "inheritance", "Synthetic trio data support de novo occurrence."),
                ]),
                variant("GC001-V3", "2", 1200103, "G", "A", "CFC1", "missense", "heterozygous", "unknown", 0.08, [
                    evidence("GC001-E7", "against", "strong", "population", "The allele is common in the synthetic population."),
                ]),
                variant("GC001-V4", "3", 1300104, "T", "C", None, "intergenic", "heterozygous", "unknown", 0.21, []),
            ],
        )
    )
    truths.append(truth("GC-001", ["GC001-V2"], "The regulatory candidate combines exact context and inheritance support; the coding assay decoy has stronger contextual counterevidence.", ["GC001-E4", "GC001-E5", "GC001-E6"], "challenging", ["molecular_decoy", "phenotype_mismatch", "regulatory"] ))

    cases.append(
        case(
            "GC-002",
            "Synthetic recessive energy-storage phenotype with a single-allele truncation decoy.",
            ["synthetic fasting collapse", "synthetic storage-product accumulation"],
            "autosomal recessive",
            ["similarly affected synthetic sibling"],
            [
                variant("GC002-V1", "4", 2100101, "C", "T", "CFD2", "stop_gained", "heterozygous", "maternal", 0.000001, [
                    evidence("GC002-E1", "supports", "strong", "molecular", "The allele is expected to truncate CFD2."),
                    evidence("GC002-E2", "against", "strong", "inheritance", "No second CFD2 allele was found and the affected sibling did not inherit this allele."),
                ]),
                variant("GC002-V2", "5", 2200102, "G", "A", "CFE2", "missense", "homozygous", "biparental", 0.000008, [
                    evidence("GC002-E3", "supports", "moderate", "functional", "A synthetic enzyme assay reports residual activity below the benchmark reference range."),
                    evidence("GC002-E4", "supports", "strong", "phenotype_context", "CFE2 synthetic biology concerns the observed storage product."),
                    evidence("GC002-E5", "supports", "strong", "inheritance", "Both affected siblings are homozygous and both unaffected parents are heterozygous."),
                ]),
                variant("GC002-V3", "6", 2300103, "A", "G", "CFF2", "synonymous", "homozygous", "biparental", 0.18, [
                    evidence("GC002-E6", "against", "strong", "population", "The allele is common in the synthetic population."),
                ]),
                variant("GC002-V4", "7", 2400104, "T", "A", "CFG2", "intronic", "heterozygous", "paternal", 0.003, [
                    evidence("GC002-E7", "uncertain", "weak", "molecular", "No synthetic splice assay is available."),
                ]),
            ],
        )
    )
    truths.append(truth("GC-002", ["GC002-V2"], "The homozygous CFE2 candidate fits function, context, and segregation; the truncation is an inheritance decoy.", ["GC002-E3", "GC002-E4", "GC002-E5"], "challenging", ["inheritance_mismatch", "single_allele_decoy"] ))

    cases.append(
        case(
            "GC-003",
            "Synthetic multisystem case with partial phenotype overlap and one unresolved candidate.",
            ["synthetic episodic ataxia", "synthetic mild cardiomyopathy"],
            "dominant with variable expression",
            ["one mildly affected synthetic relative"],
            [
                variant("GC003-V1", "8", 3100101, "G", "T", "CFH3", "missense", "heterozygous", "familial", 0.00002, [
                    evidence("GC003-E1", "supports", "strong", "functional", "A synthetic protein-stability assay reports a reproducible defect."),
                    evidence("GC003-E2", "supports", "moderate", "phenotype_context", "The invented CFH3 spectrum includes episodic ataxia."),
                    evidence("GC003-E3", "against", "weak", "phenotype_context", "Cardiomyopathy has not been described in the synthetic CFH3 record."),
                ]),
                variant("GC003-V2", "9", 3200102, "C", "A", "CFI3", "stop_gained", "heterozygous", "de novo", 0.000001, [
                    evidence("GC003-E4", "supports", "strong", "molecular", "The allele introduces an early stop."),
                    evidence("GC003-E5", "against", "strong", "phenotype_context", "The invented CFI3 phenotype is an isolated dental trait with no neurological or cardiac overlap."),
                ]),
                variant("GC003-V3", "10", 3300103, "A", "G", "CFJ3", "regulatory", "heterozygous", "unknown", None, [
                    evidence("GC003-E6", "uncertain", "moderate", "regulatory", "The variant overlaps a synthetic open-chromatin region but has no allele-specific assay."),
                ]),
                variant("GC003-V4", "11", 3400104, "T", "C", "CFK3", "missense", "heterozygous", "unknown", 0.12, [
                    evidence("GC003-E7", "against", "strong", "population", "Frequency is incompatible with the proposed rare dominant model."),
                ]),
            ],
        )
    )
    truths.append(truth("GC-003", ["GC003-V1"], "Partial context mismatch should remain visible, but the combined functional and neurological overlap warrants expert attention.", ["GC003-E1", "GC003-E2", "GC003-E3"], "conflicting", ["partial_phenotype", "valid_conflict"] ))

    cases.append(
        case(
            "GC-004",
            "Synthetic dominant renal-development phenotype with incomplete penetrance.",
            ["synthetic renal hypoplasia", "synthetic electrolyte imbalance"],
            "autosomal dominant with incomplete penetrance",
            ["one older unaffected carrier"],
            [
                variant("GC004-V1", "12", 4100101, "A", "C", "CFL4", "missense", "heterozygous", "familial", 0.000004, [
                    evidence("GC004-E1", "supports", "strong", "functional", "A synthetic transcription assay shows substantial activity loss."),
                    evidence("GC004-E2", "supports", "strong", "phenotype_context", "The invented CFL4 record matches renal hypoplasia and electrolyte findings."),
                    evidence("GC004-E3", "uncertain", "strong", "inheritance", "An older unaffected synthetic relative carries the allele, consistent with either incomplete penetrance or non-causality."),
                ]),
                variant("GC004-V2", "13", 4200102, "C", "T", "CFM4", "stop_gained", "heterozygous", "de novo", 0.000002, [
                    evidence("GC004-E4", "supports", "strong", "molecular", "The allele truncates CFM4."),
                    evidence("GC004-E5", "against", "strong", "phenotype_context", "The invented CFM4 phenotype concerns hair texture only."),
                ]),
                variant("GC004-V3", "14", 4300103, "G", "A", "CFN4", "synonymous", "heterozygous", "unknown", 0.04, []),
                variant("GC004-V4", "15", 4400104, "T", "G", None, "intergenic", "heterozygous", "unknown", 0.3, []),
            ],
        )
    )
    truths.append(truth("GC-004", ["GC004-V1"], "The candidate remains review-relevant despite unresolved penetrance because functional and context evidence are strong.", ["GC004-E1", "GC004-E2", "GC004-E3"], "conflicting", ["incomplete_penetrance", "uncertainty_retention"] ))

    cases.append(
        case(
            "GC-005",
            "Synthetic developmental speech phenotype with a validated enhancer candidate and coding decoy.",
            ["synthetic severe speech delay", "synthetic oromotor dyspraxia"],
            "de novo dominant",
            ["no similarly affected synthetic relatives"],
            [
                variant("GC005-V1", "16", 5100101, "G", "A", "CFO5", "regulatory", "heterozygous", "de novo", 0.000001, [
                    evidence("GC005-E1", "supports", "strong", "regulatory", "Allele-specific synthetic reporter data show reduced enhancer activity."),
                    evidence("GC005-E2", "supports", "moderate", "phenotype_context", "The enhancer targets a synthetic gene matching speech and oromotor findings."),
                    evidence("GC005-E3", "supports", "strong", "inheritance", "Synthetic trio data support de novo occurrence."),
                ]),
                variant("GC005-V2", "17", 5200102, "C", "T", "CFP5", "stop_gained", "heterozygous", "de novo", 0.000001, [
                    evidence("GC005-E4", "supports", "strong", "molecular", "The allele causes an early stop."),
                    evidence("GC005-E5", "against", "strong", "phenotype_context", "The invented CFP5 phenotype is isolated retinal degeneration."),
                    evidence("GC005-E6", "against", "moderate", "provenance", "The truncation statement is computational only and lacks a synthetic transcript record."),
                ]),
                variant("GC005-V3", "18", 5300103, "A", "G", "CFQ5", "missense", "heterozygous", "inherited from unaffected parent", 0.002, [
                    evidence("GC005-E7", "against", "moderate", "inheritance", "The allele was inherited from an unaffected synthetic parent."),
                ]),
                variant("GC005-V4", "19", 5400104, "T", "C", None, "intergenic", "heterozygous", "unknown", 0.11, []),
            ],
        )
    )
    truths.append(truth("GC-005", ["GC005-V1"], "The noncoding enhancer candidate has direct regulatory, context, and de novo support.", ["GC005-E1", "GC005-E2", "GC005-E3"], "challenging", ["noncoding", "coding_decoy", "provenance"] ))

    cases.append(
        case(
            "GC-006",
            "Synthetic dominant immune-signaling phenotype with a dramatic but common truncation.",
            ["synthetic recurrent sterile inflammation", "synthetic signaling-marker elevation"],
            "rare dominant",
            ["multiple unaffected older relatives"],
            [
                variant("GC006-V1", "20", 6100101, "A", "T", "CFR6", "stop_gained", "heterozygous", "familial", 0.015, [
                    evidence("GC006-E1", "supports", "strong", "molecular", "The alternate allele is expected to truncate CFR6."),
                    evidence("GC006-E2", "against", "strong", "population", "The synthetic frequency is too high for the proposed rare dominant model."),
                    evidence("GC006-E3", "against", "strong", "inheritance", "Several unaffected older synthetic relatives carry the allele."),
                ]),
                variant("GC006-V2", "21", 6200102, "G", "C", "CFS6", "missense", "heterozygous", "de novo", 0.000003, [
                    evidence("GC006-E4", "supports", "moderate", "functional", "A synthetic signaling assay reports reproducible pathway activation."),
                    evidence("GC006-E5", "supports", "strong", "phenotype_context", "The invented CFS6 phenotype matches sterile inflammation and the marker pattern."),
                    evidence("GC006-E6", "supports", "strong", "inheritance", "Synthetic trio data support de novo occurrence."),
                ]),
                variant("GC006-V3", "22", 6300103, "C", "T", "CFT6", "intronic", "heterozygous", "unknown", 0.006, [
                    evidence("GC006-E7", "uncertain", "weak", "molecular", "No splice effect was observed in one unstimulated synthetic assay."),
                ]),
                variant("GC006-V4", "1", 6400104, "T", "G", "CFU6", "synonymous", "heterozygous", "unknown", 0.25, []),
            ],
        )
    )
    truths.append(truth("GC-006", ["GC006-V2"], "Moderate functional evidence with exact context and inheritance support outweighs the common familial truncation decoy.", ["GC006-E4", "GC006-E5", "GC006-E6"], "challenging", ["population_counterevidence", "dramatic_consequence_decoy"] ))

    cases.append(
        case(
            "GC-007",
            "Synthetic X-linked motor phenotype with zygosity and inheritance decoys.",
            ["synthetic childhood motor weakness", "synthetic areflexia"],
            "X-linked recessive",
            ["affected synthetic male relatives through maternal line"],
            [
                variant("GC007-V1", "X", 7100101, "C", "A", "CFV7", "stop_gained", "heterozygous", "paternal", 0.000001, [
                    evidence("GC007-E1", "supports", "strong", "molecular", "The allele introduces an early stop."),
                    evidence("GC007-E2", "against", "strong", "inheritance", "The heterozygous paternal observation does not track with the represented X-linked recessive pedigree."),
                    evidence("GC007-E3", "against", "moderate", "phenotype_context", "The invented CFV7 record concerns isolated hearing loss."),
                ]),
                variant("GC007-V2", "X", 7200102, "G", "T", "CFW7", "missense", "hemizygous", "maternal", 0.000004, [
                    evidence("GC007-E4", "supports", "moderate", "functional", "A synthetic motor-neuron assay reports reduced protein localization."),
                    evidence("GC007-E5", "supports", "strong", "phenotype_context", "The invented CFW7 phenotype matches motor weakness and areflexia."),
                    evidence("GC007-E6", "supports", "strong", "inheritance", "The hemizygous allele tracks through the represented maternal lineage."),
                ]),
                variant("GC007-V3", "2", 7300103, "A", "G", "CFX7", "missense", "heterozygous", "unknown", 0.09, [
                    evidence("GC007-E7", "against", "strong", "population", "The allele is common in the synthetic population."),
                ]),
                variant("GC007-V4", "3", 7400104, "T", "C", None, "intergenic", "unknown", "unknown", None, []),
            ],
        )
    )
    truths.append(truth("GC-007", ["GC007-V2"], "The hemizygous CFW7 candidate fits represented function, phenotype, and X-linked inheritance.", ["GC007-E4", "GC007-E5", "GC007-E6"], "challenging", ["inheritance_decoy", "x_linked"] ))

    cases.append(
        case(
            "GC-008",
            "Synthetic neurodevelopmental case with two distinct plausible mechanisms.",
            ["synthetic developmental delay", "synthetic movement disorder"],
            "genetically heterogeneous",
            ["family structure is uninformative"],
            [
                variant("GC008-V1", "4", 8100101, "A", "G", "CFY8", "missense", "heterozygous", "unknown", 0.000003, [
                    evidence("GC008-E1", "supports", "strong", "functional", "A synthetic neuronal assay reports a severe trafficking defect."),
                    evidence("GC008-E2", "supports", "strong", "phenotype_context", "The invented CFY8 phenotype matches both major findings."),
                ]),
                variant("GC008-V2", "5", 8200102, "C", "T", "CFZ8", "regulatory", "heterozygous", "unknown", 0.000005, [
                    evidence("GC008-E3", "supports", "moderate", "regulatory", "A synthetic enhancer assay reports allele-specific expression loss."),
                    evidence("GC008-E4", "supports", "moderate", "phenotype_context", "CFZ8 synthetic expression and phenotype overlap the movement disorder."),
                    evidence("GC008-E5", "uncertain", "weak", "inheritance", "Parental samples are unavailable in the synthetic context."),
                ]),
                variant("GC008-V3", "6", 8300103, "G", "A", "CGA8", "stop_gained", "heterozygous", "de novo", 0.000001, [
                    evidence("GC008-E6", "supports", "strong", "molecular", "The allele is expected to truncate CGA8."),
                    evidence("GC008-E7", "against", "strong", "phenotype_context", "The invented CGA8 phenotype is an isolated blood-cell trait."),
                ]),
                variant("GC008-V4", "7", 8400104, "T", "A", "CGB8", "intronic", "heterozygous", "unknown", None, [
                    evidence("GC008-E8", "uncertain", "weak", "molecular", "No functional or transcript evidence is available."),
                ]),
            ],
        )
    )
    truths.append(truth("GC-008", ["GC008-V1", "GC008-V2"], "Two mechanistically distinct candidates warrant expert attention; the coding truncation is a context decoy.", ["GC008-E1", "GC008-E2", "GC008-E3", "GC008-E4", "GC008-E5"], "challenging", ["multiple_plausible", "heterogeneity", "regulatory"] ))

    cases.append(
        case(
            "GC-009",
            "Synthetic negative control with molecularly interesting but context-incompatible candidates.",
            ["synthetic isolated liver enzyme elevation"],
            "unknown",
            ["no segregation information"],
            [
                variant("GC009-V1", "8", 9100101, "C", "G", "CGC9", "stop_gained", "heterozygous", "unknown", 0.00001, [
                    evidence("GC009-E1", "supports", "strong", "molecular", "The allele is expected to truncate CGC9."),
                    evidence("GC009-E2", "against", "strong", "phenotype_context", "The invented CGC9 phenotype is isolated skeletal dysplasia."),
                ]),
                variant("GC009-V2", "9", 9200102, "A", "T", "CGD9", "missense", "heterozygous", "unknown", 0.03, [
                    evidence("GC009-E3", "against", "strong", "population", "The allele is too common for the proposed rare context."),
                ]),
                variant("GC009-V3", "10", 9300103, "G", "A", "CGE9", "regulatory", "heterozygous", "unknown", None, [
                    evidence("GC009-E4", "uncertain", "weak", "regulatory", "The locus overlaps a synthetic enhancer without allele-specific evidence."),
                ]),
                variant("GC009-V4", "11", 9400104, "T", "C", None, "intergenic", "heterozygous", "unknown", 0.4, []),
            ],
        )
    )
    truths.append(truth("GC-009", [], "No candidate has sufficient context-compatible evidence for expert shortlisting.", [], "challenging", ["negative_control", "molecular_decoy"] ))

    cases.append(
        case(
            "GC-010",
            "Synthetic insufficient-evidence control with only weak unvalidated observations.",
            ["synthetic nonspecific fatigue", "synthetic mild laboratory abnormality"],
            "unknown",
            ["no family samples"],
            [
                variant("GC010-V1", "12", 10100101, "A", "G", "CGF0", "missense", "heterozygous", "unknown", None, [evidence("GC010-E1", "uncertain", "weak", "functional", "A single unreplicated synthetic assay showed a small effect.")]),
                variant("GC010-V2", "13", 10200102, "C", "T", "CGG0", "intronic", "heterozygous", "unknown", None, [evidence("GC010-E2", "uncertain", "weak", "molecular", "A computational splice flag has no synthetic transcript validation.")]),
                variant("GC010-V3", "14", 10300103, "G", "C", "CGH0", "regulatory", "heterozygous", "unknown", None, [evidence("GC010-E3", "uncertain", "weak", "regulatory", "The locus is open chromatin in one unrelated synthetic tissue.")]),
                variant("GC010-V4", "15", 10400104, "T", "A", None, "intergenic", "heterozygous", "unknown", None, []),
            ],
        )
    )
    truths.append(truth("GC-010", [], "The safe result is an insufficient-evidence abstention.", [], "ambiguous", ["negative_control", "insufficient_evidence"] ))

    cases.append(
        case(
            "GC-011",
            "Synthetic recessive ciliary phenotype with a phased pair and a de novo truncation decoy.",
            ["synthetic laterality defect", "synthetic chronic airway disease"],
            "autosomal recessive",
            ["one similarly affected synthetic sibling"],
            [
                variant("GC011-V1", "16", 11100101, "G", "A", "CGI1", "splice_region", "heterozygous", "maternal", 0.000006, [
                    evidence("GC011-E1", "supports", "moderate", "functional", "Synthetic RNA shows partial exon skipping."),
                    evidence("GC011-E2", "supports", "strong", "inheritance", "The allele is in trans with GC011-V2 in both affected siblings."),
                ]),
                variant("GC011-V2", "16", 11100202, "C", "T", "CGI1", "missense", "heterozygous", "paternal", 0.000009, [
                    evidence("GC011-E3", "supports", "moderate", "functional", "A synthetic ciliary-motion assay reports reduced activity."),
                    evidence("GC011-E4", "supports", "strong", "phenotype_context", "The invented CGI1 phenotype matches laterality and airway findings."),
                    evidence("GC011-E5", "supports", "strong", "inheritance", "The allele is in trans with GC011-V1 in both affected siblings."),
                ]),
                variant("GC011-V3", "17", 11200103, "A", "T", "CGJ1", "stop_gained", "heterozygous", "de novo", 0.000001, [
                    evidence("GC011-E6", "supports", "strong", "molecular", "The allele is expected to truncate CGJ1."),
                    evidence("GC011-E7", "against", "strong", "phenotype_context", "The invented CGJ1 phenotype concerns isolated pigmentation."),
                ]),
                variant("GC011-V4", "18", 11300104, "T", "C", "CGK1", "synonymous", "heterozygous", "unknown", 0.2, []),
            ],
        )
    )
    truths.append(truth("GC-011", ["GC011-V1", "GC011-V2"], "The phased CGI1 pair jointly fits function, phenotype, and represented recessive inheritance.", ["GC011-E1", "GC011-E2", "GC011-E3", "GC011-E4", "GC011-E5"], "challenging", ["compound_heterozygous", "inheritance_decoy"] ))

    cases.append(
        case(
            "GC-012",
            "Synthetic recessive cartilage phenotype with a dominant-appearing context decoy.",
            ["synthetic short stature", "synthetic joint laxity"],
            "autosomal recessive",
            ["unaffected parents are related in the synthetic pedigree"],
            [
                variant("GC012-V1", "19", 12100101, "C", "A", "CGL2", "missense", "homozygous", "biparental", 0.00002, [
                    evidence("GC012-E1", "supports", "moderate", "functional", "A synthetic matrix assay shows moderately reduced assembly."),
                    evidence("GC012-E2", "supports", "strong", "phenotype_context", "The invented CGL2 phenotype matches short stature and joint laxity."),
                    evidence("GC012-E3", "supports", "strong", "inheritance", "The homozygous allele is biparentally inherited."),
                ]),
                variant("GC012-V2", "20", 12200102, "G", "T", "CGM2", "missense", "heterozygous", "de novo", 0.000001, [
                    evidence("GC012-E4", "supports", "strong", "functional", "A synthetic matrix assay shows severe disruption."),
                    evidence("GC012-E5", "supports", "moderate", "phenotype_context", "The invented CGM2 phenotype partially overlaps joint laxity."),
                    evidence("GC012-E6", "against", "strong", "inheritance", "The represented CGM2 mechanism requires a second allele, which is absent."),
                ]),
                variant("GC012-V3", "21", 12300103, "A", "G", "CGN2", "stop_gained", "heterozygous", "maternal", 0.004, [evidence("GC012-E7", "against", "strong", "phenotype_context", "The invented CGN2 phenotype is unrelated to cartilage.")]),
                variant("GC012-V4", "22", 12400104, "T", "C", None, "intergenic", "heterozygous", "unknown", 0.19, []),
            ],
        )
    )
    truths.append(truth("GC-012", ["GC012-V1"], "The homozygous CGL2 candidate fits represented function, context, and inheritance; CGM2 is a mechanism mismatch.", ["GC012-E1", "GC012-E2", "GC012-E3"], "challenging", ["mechanism_mismatch", "partial_phenotype"] ))

    cases.append(
        case(
            "GC-013",
            "Synthetic sparse-evidence neurological case where a plausible candidate should remain explicitly uncertain.",
            ["synthetic episodic tremor", "synthetic mild coordination difficulty"],
            "autosomal dominant suspected",
            ["two mildly affected synthetic relatives"],
            [
                variant("GC013-V1", "1", 13100101, "A", "C", "CGO3", "intronic", "heterozygous", "familial", 0.00003, [
                    evidence("GC013-E1", "supports", "moderate", "inheritance", "The allele tracks with the mild phenotype in the small synthetic family."),
                    evidence("GC013-E2", "uncertain", "weak", "molecular", "A splice prediction lacks synthetic transcript validation."),
                    evidence("GC013-E3", "supports", "moderate", "phenotype_context", "The invented CGO3 phenotype partially overlaps episodic tremor."),
                ]),
                variant("GC013-V2", "2", 13200102, "G", "A", "CGP3", "stop_gained", "heterozygous", "de novo", 0.000001, [
                    evidence("GC013-E4", "supports", "strong", "molecular", "The allele is expected to truncate CGP3."),
                    evidence("GC013-E5", "against", "strong", "phenotype_context", "The invented CGP3 phenotype is a congenital kidney anomaly."),
                ]),
                variant("GC013-V3", "3", 13300103, "C", "T", "CGQ3", "missense", "heterozygous", "unknown", 0.07, [evidence("GC013-E6", "against", "strong", "population", "The allele is too common for the proposed model.")]),
                variant("GC013-V4", "4", 13400104, "T", "G", None, "intergenic", "heterozygous", "unknown", None, []),
            ],
        )
    )
    truths.append(truth("GC-013", ["GC013-V1"], "The sparse CGO3 candidate warrants expert review only with explicit insufficient/uncertain evidence labeling.", ["GC013-E1", "GC013-E2", "GC013-E3"], "ambiguous", ["insufficient_evidence", "uncertainty_retention"] ))

    return cases, truths


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    cases, truths = build_records()
    write_jsonl(CASES_PATH, cases)
    write_jsonl(TRUTH_PATH, truths)
    manifest = {
        "freeze_id": "benchmark_conflict_v1",
        "frozen_at_utc": "2026-08-29T00:00:00+00:00",
        "hash_algorithm": "sha256",
        "case_count": len(cases),
        "positive_case_count": sum(bool(item["relevant_variant_ids"]) for item in truths),
        "negative_control_count": sum(not item["relevant_variant_ids"] for item in truths),
        "created_before_arbitration_spec": True,
        "artifacts": {
            "data/cases/benchmark_conflict_v1.jsonl": sha256(CASES_PATH),
            "data/ground_truth/benchmark_conflict_v1_ground_truth.jsonl": sha256(TRUTH_PATH),
            "scripts/build_conflict_benchmark.py": sha256(Path(__file__)),
        },
        "safety_disclaimer": SAFETY,
        "notes": [
            "All cases, loci, genes, contexts, evidence, and labels are fully synthetic.",
            "Ground truth is stored separately and is not loaded by system runners.",
            "The benchmark was frozen before conflict-arbitration rules were specified or implemented.",
        ],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"Frozen benchmark_conflict_v1: {len(cases)} cases; "
        f"cases_sha256={manifest['artifacts']['data/cases/benchmark_conflict_v1.jsonl']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
