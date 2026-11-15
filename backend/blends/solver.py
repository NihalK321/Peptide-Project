"""Score a candidate pool, solve its QUBO, and report an exact reference."""

from math import comb
from time import perf_counter
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
from qiskit import qasm2
from scipy.optimize import minimize

from .models import BlendRequest, ShortlistRequest
from .quantum import build_blend_circuit, probabilities, qubo_to_ising
from .scoring import LIMITATIONS, METHOD, score_candidate
from .qubo import build_qubo, DescriptorExperiment
from .validation import verify_qubo


def shortlist(catalog, request: ShortlistRequest):
    started = perf_counter()
    records, stats = catalog.load()
    query = request.search.strip().casefold()
    scored = []
    for record in records:
        if not request.min_length <= len(record["sequence"]) <= request.max_length:
            continue
        if query and query not in f"{record['name']} {record['sequence']} {record['accession']}".casefold():
            continue
        scored.append(score_candidate(record, request))
    scored.sort(key=lambda row: (-row["score"], row["id"]))
    # Equal sequences were already deduplicated by the catalog adapter.
    return {"contract_version": "1.0", "candidates": scored[:request.pool_size],
            "catalog": stats, "scored_count": len(scored), "goals": request.model_dump(),
            "shortlist_method": "Classical ranking by individual chemical-property score; may exclude the best diverse blend outside this pool.",
            "elapsed_seconds": perf_counter() - started, "scoring_method": METHOD, "limitations": LIMITATIONS}


def make_qubo(candidates, blend_size, diversity_weight):
    """Keep the existing public helper; delegate its math to validated inputs."""
    return build_qubo(candidates, blend_size, diversity_weight)


def optimize_blend(catalog, request: BlendRequest):
    started = perf_counter()
    records, stats = catalog.load()
    by_id = {record["id"]: record for record in records}
    missing = [identifier for identifier in request.candidate_ids if identifier not in by_id]
    if missing:
        raise ValueError("Some candidate IDs are unavailable or require unsupported chemical modifications; refresh the pool.")
    if any(len(by_id[identifier]["sequence"]) > 60 for identifier in request.candidate_ids):
        raise ValueError("Blend descriptor calculations support sequences of at most 60 residues.")
    candidates = [score_candidate(by_id[identifier], request) for identifier in request.candidate_ids]
    return solve_scored_candidates(candidates, request, stats, started=started)


def optimize_descriptor_input(experiment: DescriptorExperiment):
    """Backend-only handoff; supplied descriptors retain their own provenance."""
    result = solve_scored_candidates(experiment.scored_candidates(), experiment.request(),
        {"input_source": "explicit_descriptor_contract", "descriptors_independently_verified": False},
        pair_terms=experiment.pair_terms)
    result["scoring_method"] = {**result["scoring_method"],
        "library": "Caller-supplied descriptors; original methods and provenance are retained per candidate",
        "charge": "Supplied net charge in e at the requested pH; not independently verified",
        "hydropathy": "Supplied dimensionless Kyte-Doolittle GRAVY; not independently verified",
        "mass": "Optional supplied average molecular mass in Da; not used in scoring"}
    return result


def solve_scored_candidates(candidates, request: BlendRequest, stats, pair_terms=None, started=None):
    """Reuse the existing QAOA circuit, COBYLA fitting and simulated shot sampling."""
    started = perf_counter() if started is None else started
    if [candidate["id"] for candidate in candidates] != request.candidate_ids:
        raise ValueError("Candidate order must match request IDs exactly.")
    model = build_qubo(candidates, request.blend_size, request.diversity_weight, pair_terms)
    validation, exact_subsets = verify_qubo(model, candidates, request.blend_size, request.diversity_weight)
    energies = model["energies"]
    feasible = model["states"].sum(axis=1) == request.blend_size
    feasible_indices = np.flatnonzero(feasible)
    exact_index = int(feasible_indices[np.argmin(model["raw_cost"][feasible_indices])])
    exact_cost = float(model["raw_cost"][exact_index])
    optimal = feasible & np.isclose(model["raw_cost"], exact_cost, rtol=0, atol=1e-8)
    offset, fields, couplings = qubo_to_ising(model["constant"], model["linear"], model["quadratic"])
    # Scale by the largest gate coefficient, rather than the entire energy
    # range, so a useful gamma need not grow with the number of bitstrings.
    energy_scale = max(float(np.max(np.abs(fields))), float(np.max(np.abs(couplings))), 1e-12)
    normalized = (energies - energies.min()) / energy_scale
    rng = np.random.default_rng(request.seed)
    history = []

    def objective(parameters):
        distribution = probabilities(fields, couplings, parameters, energy_scale)
        value = float(distribution @ normalized)
        history.append({"evaluation": len(history) + 1, "expected_penalized_objective": float(distribution @ energies),
                        "feasible_probability": float(distribution[feasible].sum())})
        return value

    initial = rng.uniform(0.1, np.pi, 2 * request.layers)
    fitted = minimize(objective, initial, method="COBYLA", options={"maxiter": request.max_iterations})
    distribution = np.maximum(probabilities(fields, couplings, fitted.x, energy_scale), 0)
    distribution /= distribution.sum()
    samples = rng.multinomial(request.shots, distribution)
    feasible_observed = np.flatnonzero(feasible & (samples > 0))
    best_index = int(feasible_observed[np.argmin(model["raw_cost"][feasible_observed])]) if len(feasible_observed) else None
    size = len(candidates)

    def selection(index):
        if index is None:
            return None
        selected_indices = np.flatnonzero(model["states"][index]).tolist()
        selected = [candidates[i] for i in selected_indices]
        return {"bitstring": format(index, f"0{size}b"), "candidate_ids": [candidate["id"] for candidate in selected],
                "candidates": selected, "objective": float(model["raw_cost"][index]),
                "individual_score_sum": sum(candidate["score"] for candidate in selected),
                "weighted_redundancy_penalty": float(request.diversity_weight * sum(
                    model["overlap"][i, j] for i in selected_indices for j in selected_indices if i < j))}

    circuit = build_blend_circuit(fields, couplings, fitted.x, energy_scale)
    # RZZ(a) = CX -> RZ(a) -> CX, for portable Composer output.
    # Build the portable export explicitly, avoiding hardware plugin loading.
    from qiskit import QuantumCircuit
    expanded = QuantumCircuit(size)
    for instruction in circuit.data:
        qubits = [circuit.find_bit(q).index for q in instruction.qubits]
        if instruction.operation.name == "rzz":
            expanded.cx(*qubits)
            expanded.rz(instruction.operation.params[0], qubits[1])
            expanded.cx(*qubits)
        else:
            expanded.append(instruction.operation, qubits)

    return {"contract_version": "1.0", "provenance": "simulated", "execution_backend": "qiskit_statevector",
        "experiment_id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_ids": request.candidate_ids, "validation": validation,
        "catalog": stats, "goals": request.model_dump(), "candidates": candidates,
        "selected_blend": selection(best_index), "classical_reference": selection(exact_index),
        "benchmark": {"pool_size": size, "qubits": size, "bitstring_count": 2 ** size,
            "feasible_subset_count": comb(size, request.blend_size),
            "feasible_probability": float(distribution[feasible].sum()),
            "observed_feasibility_rate": int(samples[feasible].sum()) / request.shots,
            "optimum_probability": float(distribution[optimal].sum()),
            "uniform_optimum_probability": int(optimal.sum()) / 2 ** size,
            "uniform_feasible_probability": comb(size, request.blend_size) / 2 ** size,
            "sampled_objective_gap": None if best_index is None else float(model["raw_cost"][best_index] - exact_cost)},
        "counts": {format(i, f"0{size}b"): int(count) for i, count in enumerate(samples) if count},
        "sampling": {"method": "seeded multinomial sampling of the ideal Qiskit statevector distribution",
            "feasible_counts": {format(i, f"0{size}b"): int(samples[i]) for i in np.flatnonzero(feasible & (samples > 0))},
            "infeasible_counts": {format(i, f"0{size}b"): int(samples[i]) for i in np.flatnonzero(~feasible & (samples > 0))},
            "feasible_shots": int(samples[feasible].sum()), "infeasible_shots": int(samples[~feasible].sum()),
            "observed_frequencies": {format(i, f"0{size}b"): int(samples[i]) / request.shots for i in np.flatnonzero(samples)}},
        "probabilities": {format(i, f"0{size}b"): float(value) for i, value in enumerate(distribution)},
        "qubo": {"constant": model["constant"], "linear": model["linear"].tolist(),
            "matrix_upper_triangle": model["matrix_upper_triangle"].tolist(),
            "evaluation_convention": "constant + x.T @ matrix_upper_triangle @ x; each i<j pair occurs once",
            "candidate_ids_in_qubit_order": request.candidate_ids,
            "pair_method": "sequence_bigram_jaccard" if pair_terms is None else "explicit_redundancy_terms",
            "explicit_pair_terms": None if pair_terms is None else [term.model_dump() for term in pair_terms],
            "quadratic_upper_triangle": model["quadratic"].tolist(), "cardinality_penalty": model["penalty"],
            "pair_overlap_upper_triangle": model["overlap"].tolist()},
        "ising": {"offset": offset, "fields": fields.tolist(), "couplings_upper_triangle": couplings.tolist()},
        "classical_feasible_selections": exact_subsets,
        "circuit_metadata": {"implementation": "backend.blends.quantum.build_blend_circuit",
            "qubits": size, "layers": request.layers, "parameter_count": len(fitted.x),
            "gate_counts": dict(circuit.count_ops()), "energy_scale": energy_scale,
            "phase_convention": "exp(-i*gamma*(H-offset*I)/energy_scale); offset omitted as a global phase",
            "optimizer_objective": "expectation of (QUBO_energy-min(QUBO_energy))/energy_scale",
            "classical_optimizer": "scipy.optimize.minimize COBYLA",
            "parameter_order": "gamma_0,beta_0,gamma_1,beta_1,...",
            "probability_provenance": "ideal_statevector", "counts_provenance": "simulated_shots"},
        "circuit_qasm": qasm2.dumps(expanded), "parameters": fitted.x.tolist(),
        "circuit_depth": circuit.depth(), "history": history,
        "converged": bool(fitted.success), "optimizer_message": str(fitted.message),
        "evaluations": int(fitted.nfev), "shots": request.shots, "elapsed_seconds": perf_counter() - started,
        "bit_order": "Rightmost bit selects candidate 0; 1 means include the whole peptide.",
        "scoring_method": {**METHOD, **({"pair_penalty": "Explicit normalized sequence-redundancy penalties; see qubo.explicit_pair_terms"} if pair_terms is not None else {})}, "limitations": LIMITATIONS,
        "status": "completed" if best_index is not None else "no_feasible_sample"}
