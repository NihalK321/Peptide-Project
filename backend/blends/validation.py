"""Exhaustive independent checks for the bounded peptide selection model."""

from itertools import combinations
from math import comb

import numpy as np

from .quantum import qubo_to_ising


def verify_qubo(model, candidates, selection_count, pair_weight):
    """Check every state and every feasible subset, failing before QAOA on error."""
    size = len(candidates)
    offset, fields, couplings = qubo_to_ising(model["constant"], model["linear"], model["quadratic"])
    direct, matrix_values, ising_values = [], [], []
    feasible = []
    for index in range(2 ** size):
        bits = np.array([(index >> i) & 1 for i in range(size)])
        selected = np.flatnonzero(bits)
        value = -sum(candidates[i]["score"] for i in selected)
        value += pair_weight * sum(model["overlap"][i, j] for i, j in combinations(selected, 2))
        value += model["penalty"] * (len(selected) - selection_count) ** 2
        direct.append(value)
        matrix_values.append(model["constant"] + bits @ model["matrix_upper_triangle"] @ bits)
        z = 1 - 2 * bits
        ising_values.append(offset + fields @ z + sum(couplings[i, j] * z[i] * z[j] for i, j in combinations(range(size), 2)))
        feasible.append(len(selected) == selection_count)
    direct, feasible = np.array(direct), np.array(feasible)
    errors = {
        "direct_vs_qubo_max_error": float(np.max(np.abs(direct - model["energies"]))),
        "matrix_vs_qubo_max_error": float(np.max(np.abs(matrix_values - model["energies"]))),
        "ising_vs_qubo_max_error": float(np.max(np.abs(ising_values - model["energies"]))),
    }
    separated = bool(direct[~feasible].min() > direct[feasible].max())
    if max(errors.values()) > 1e-9 or not separated or int(feasible.sum()) != comb(size, selection_count):
        raise ValueError(f"Exhaustive QUBO validation failed: {errors}; cardinality separation={separated}")
    subsets = []
    for chosen in combinations(range(size), selection_count):
        index = sum(1 << i for i in chosen)
        subsets.append({"bitstring": format(index, f"0{size}b"),
                        "candidate_ids": [candidates[i]["id"] for i in chosen],
                        "objective": float(model["raw_cost"][index])})
    return {"passed": True, "checked_binary_states": 2 ** size,
            "checked_feasible_subsets": len(subsets), "cardinality_separation_verified": separated,
            "absolute_tolerance": 1e-9, **errors}, subsets
