"""Explicit sequence-property proxies; not predictions of mixture behavior."""

from functools import lru_cache
import Bio
from Bio.SeqUtils.ProtParam import ProteinAnalysis

from .models import ChemicalGoals


MODEL_VERSION = "sequence-research-v1"
METHOD = {
    "version": MODEL_VERSION,
    "library": f"Biopython {Bio.__version__}",
    "charge": "ProteinAnalysis.charge_at_pH; Bjellqvist pKa model; elementary-charge units",
    "hydropathy": "ProteinAnalysis.gravy; Kyte-Doolittle mean residue hydropathy (dimensionless)",
    "mass": "ProteinAnalysis.molecular_weight; average isotopic mass, Da; linear free-termini peptide",
    "charge_score": "1 / (1 + abs(charge - target_charge) / 2); fixed charge tolerance 2 e",
    "hydropathy_score": "1 / (1 + abs(GRAVY - target_hydropathy)); fixed tolerance 1 GRAVY unit",
    "candidate_score": "Weighted mean of charge_score and hydropathy_score; normalized to [0,1]",
    "pair_penalty": "Jaccard overlap of unique adjacent residue pairs; sequence-redundancy proxy in [0,1]",
    "objective": "-sum(score_i*x_i) + diversity_weight*sum(overlap_ij*x_i*x_j) + lambda*(sum(x)-k)^2",
}
LIMITATIONS = [
    "Research selection of whole peptide references, not a physical blend simulation or dosing recommendation.",
    "Calculated free-termini sequence descriptors ignore 3D structure, solvent, chemical modifications, and interactions.",
    "Records with documented modifications are excluded; absent modification annotations do not verify a chemical form.",
    "Charge estimates and hydropathy are model-dependent; no calibrated uncertainty or experimental validation is supplied.",
    "Targets apply to individual candidate descriptors; mixture charge, solubility, compatibility, and efficacy are not predicted.",
    "Sequence redundancy is a diversity preference, not a measured peptide-peptide interaction or synergy.",
    "Classical filtering creates the small pool; QAOA runs only on that pool, not the entire database.",
    "The exact reference is optimal only within the supplied pool and objective; no quantum speedup is claimed.",
    "QAOA results use ideal statevector simulation and simulated measurements, not quantum hardware.",
]


@lru_cache(maxsize=50000)
def descriptors(sequence, ph):
    analysis = ProteinAnalysis(sequence)
    return {"charge": float(analysis.charge_at_pH(ph)), "hydropathy": float(analysis.gravy()),
            "mass_da": float(analysis.molecular_weight())}


def score_candidate(record, goals: ChemicalGoals):
    values = descriptors(record["sequence"], goals.ph)
    return {**record, **values, **score_descriptors(values, goals), "provenance": "calculated", "ph": goals.ph}


def score_descriptors(values, goals: ChemicalGoals):
    """The same normalized research score for calculated or supplied descriptors."""
    charge_score = 1 / (1 + abs(values["charge"] - goals.target_charge) / 2)
    hydropathy_score = 1 / (1 + abs(values["hydropathy"] - goals.target_hydropathy))
    score = (goals.charge_weight * charge_score + goals.hydropathy_weight * hydropathy_score) / (goals.charge_weight + goals.hydropathy_weight)
    return {"charge_score": charge_score, "hydropathy_score": hydropathy_score, "score": score}


def pair_overlap(first, second):
    first_pairs = {first[i:i + 2] for i in range(len(first) - 1)}
    second_pairs = {second[i:i + 2] for i in range(len(second) - 1)}
    return len(first_pairs & second_pairs) / len(first_pairs | second_pairs)
