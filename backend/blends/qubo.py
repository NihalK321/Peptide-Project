"""Validated, dimensionless whole-peptide QUBO; each pair occurs once.

E(x) = c + x.T @ Q_upper @ x, including the diagonal of Q_upper.
Q_ii = -S_i + lambda*(1-2*k); Q_ij = w*P_ij + 2*lambda (i<j).
The lower triangle is zero, and c=lambda*k*k is retained explicitly.
"""

from typing import Literal

import numpy as np
from pydantic import Field, field_validator, model_validator

from ..schema import Model, STANDARD_AMINO_ACIDS
from .models import ChemicalGoals, BlendRequest
from .scoring import pair_overlap, score_descriptors


class ScoredCandidate(Model):
    """Mathematical input, not a claim that a score was experimentally measured."""
    id: str = Field(min_length=1, max_length=200)
    sequence: str = Field(min_length=2, max_length=60)
    score: float = Field(ge=0, le=1)

    @field_validator("sequence")
    @classmethod
    def supported_sequence(cls, sequence):
        if any(letter not in STANDARD_AMINO_ACIDS for letter in sequence):
            raise ValueError("Only uppercase standard residues in supported linear sequences are accepted.")
        return sequence


class CandidateDescriptors(Model):
    charge: float
    hydropathy: float = Field(ge=-4.5, le=4.5)
    mass_da: float | None = Field(default=None, gt=0)
    ph: float = Field(ge=2, le=12)
    method: str = Field(min_length=1)
    provenance: Literal["calculated", "published"]


class DescriptorCandidate(Model):
    id: str = Field(min_length=1, max_length=200)
    sequence: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=1)
    chemical_form: Literal["linear_free_termini"]
    descriptors: CandidateDescriptors
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    modifications: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def supported(self):
        ScoredCandidate(id=self.id, sequence=self.sequence, score=0)
        if self.modifications:
            raise ValueError("Modified candidates are unsupported by this scoring contract.")
        if abs(self.descriptors.charge) > len(self.sequence) + 1:
            raise ValueError("Charge exceeds the bound supported by this standard-residue model.")
        return self


class PairTerm(Model):
    first_id: str = Field(min_length=1)
    second_id: str = Field(min_length=1)
    penalty: float = Field(ge=0, le=1)
    method: Literal["sequence_bigram_jaccard", "researcher_supplied_redundancy"]


class DescriptorExperiment(Model):
    """Proposed backend handoff; no public API route is added automatically."""
    candidates: list[DescriptorCandidate] = Field(min_length=2, max_length=8)
    goals: ChemicalGoals = Field(default_factory=ChemicalGoals)
    selection_count: int = Field(default=3, ge=1, le=7, strict=True)
    pair_terms: list[PairTerm] | None = None
    layers: int = Field(default=1, ge=1, le=2, strict=True)
    max_iterations: int = Field(default=60, ge=10, le=120, strict=True)
    shots: int = Field(default=2048, ge=128, le=8192, strict=True)
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)

    @model_validator(mode="after")
    def consistent(self):
        self.request()  # Reuse existing pool, cardinality and execution validation.
        if any(abs(candidate.descriptors.ph - self.goals.ph) > 1e-8 for candidate in self.candidates):
            raise ValueError("Descriptor pH must match researcher target pH; recompute before optimizing.")
        pair_matrix([candidate.id for candidate in self.candidates], self.pair_terms,
                    [candidate.sequence for candidate in self.candidates])
        return self

    def request(self):
        return BlendRequest(**self.goals.model_dump(), candidate_ids=[candidate.id for candidate in self.candidates],
                            blend_size=self.selection_count, layers=self.layers,
                            max_iterations=self.max_iterations, shots=self.shots, seed=self.seed)

    def scored_candidates(self):
        rows = []
        for candidate in self.candidates:
            values = candidate.descriptors.model_dump()
            rows.append({**candidate.model_dump(), **values,
                         **score_descriptors(values, self.goals), "accession": candidate.id,
                         "descriptor_provenance": values["provenance"],
                         "provenance": "calculated", "scoring_provenance": "calculated_from_supplied_descriptors"})
        return rows


def pair_matrix(ids, terms, sequences):
    """Explicit pair inputs must cover every unordered pair, with no duplicates."""
    size = len(ids)
    matrix = np.zeros((size, size))
    if terms is None:
        for i in range(size):
            for j in range(i + 1, size):
                matrix[i, j] = pair_overlap(sequences[i], sequences[j])
        return matrix
    by_id = {identifier: i for i, identifier in enumerate(ids)}
    seen = set()
    for value in terms:
        term = value if isinstance(value, PairTerm) else PairTerm.model_validate(value)
        if term.first_id not in by_id or term.second_id not in by_id or term.first_id == term.second_id:
            raise ValueError("Each pair must refer to two distinct input peptide IDs.")
        i, j = sorted((by_id[term.first_id], by_id[term.second_id]))
        if (i, j) in seen:
            raise ValueError("Duplicate or reversed duplicate pair term.")
        if term.method == "sequence_bigram_jaccard" and not np.isclose(term.penalty, pair_overlap(sequences[i], sequences[j]), rtol=0, atol=1e-10):
            raise ValueError("A sequence_bigram_jaccard term must equal the documented sequence proxy.")
        seen.add((i, j))
        matrix[i, j] = term.penalty
    if len(seen) != size * (size - 1) // 2:
        raise ValueError("Explicit pair terms must cover every unordered pair; missing is not assumed zero.")
    return matrix


def build_qubo(candidates, blend_size, diversity_weight, pair_terms=None):
    nodes = [ScoredCandidate.model_validate({key: row.get(key) for key in ("id", "sequence", "score")}) for row in candidates]
    ids = [node.id for node in nodes]
    if not 2 <= len(nodes) <= 8 or len(set(ids)) != len(ids):
        raise ValueError("Use 2-8 unique peptide IDs.")
    if isinstance(blend_size, bool) or not isinstance(blend_size, int) or not 1 <= blend_size < len(nodes):
        raise ValueError("Select a positive integer smaller than the candidate count.")
    if not np.isfinite(diversity_weight) or not 0 <= diversity_weight <= 2:
        raise ValueError("Diversity weight must be finite and between 0 and 2.")
    scores = np.array([node.score for node in nodes])
    overlap = pair_matrix(ids, pair_terms, [node.sequence for node in nodes])
    # The raw objective lies in [-sum(S), w*sum(P)]. A unit cardinality
    # violation therefore costs more than its entire possible range.
    penalty = float(scores.sum() + diversity_weight * overlap.sum() + 1)
    constant = penalty * blend_size ** 2
    linear = -scores + penalty * (1 - 2 * blend_size)
    quadratic = diversity_weight * overlap + 2 * penalty * np.triu(np.ones_like(overlap), 1)
    states = ((np.arange(2 ** len(nodes))[:, None] >> np.arange(len(nodes))) & 1).astype(float)
    raw_cost = -states @ scores + diversity_weight * np.einsum("bi,ij,bj->b", states, overlap, states)
    energies = constant + states @ linear + np.einsum("bi,ij,bj->b", states, quadratic, states)
    return {"constant": float(constant), "linear": linear, "quadratic": quadratic,
            "matrix_upper_triangle": quadratic + np.diag(linear), "candidate_ids": ids,
            "penalty": penalty, "overlap": overlap, "states": states,
            "raw_cost": raw_cost, "energies": energies}
