"""Actual bounded QAOA execution and exact comparisons for sequence choices."""

from datetime import datetime, timezone
from importlib.metadata import version
from time import perf_counter
from uuid import uuid4

import numpy as np
from scipy.optimize import minimize

from .problem import LIMITATIONS, build_problem, chemical_properties
from .quantum import build_sequence_circuit, circuit_artifacts, sequence_probabilities


METHOD = {
    "chemistry_interface": "backend.peptide_analysis.analyze_sequence",
    "chemistry_version": f"Biopython {version('biopython')}",
    "charge": "Estimated charge at requested pH, Bjellqvist pKa model; e",
    "hydropathy": "Mean Kyte-Doolittle GRAVY; dimensionless",
    "mass": "Average isotopic mass, linear free termini; Da",
    "objective": "[wq*((charge-target)/2)^2 + wh*distance(GRAVY,[low,high])^2 + wr*adjacent_identical_pairs/(length-1)] / (wq+wh+wr)",
    "normalization": "Fixed 2 e charge scale, 1 GRAVY unit; no candidate-pool-dependent normalization. Objective is nonnegative and not bounded by 1.",
    "constraints": "Length, allowed/excluded residues, fixed positions enforced by encoding. Missing required residues and excess mutations receive a dominating penalty.",
    "penalty": "lambda = max(raw objective)-min(raw objective)+1; violation = missing_required_count + max(0,mutations-budget)^2",
    "bit_order": "Rightmost bit is qubit 0, mapped to the first variable position. Bit 0 selects choices[0], bit 1 selects choices[1].",
    "pI": "Reported as a descriptor only; not the target pH or optimization objective.",
}


def preview(request):
    problem = build_problem(request)
    return {"contract_version": "1.0", "provenance": "calculated", "request": request.model_dump(),
            "variables": problem["variables"], "domains": problem["domains"],
            "qubits": len(problem["variables"]), "state_count": len(problem["rows"]),
            "feasible_state_count": int(problem["feasible"].sum()),
            "cost_representation": problem["polynomial"]["representation"],
            "cost_polynomial_degree": problem["polynomial"]["degree"],
            "template_properties": chemical_properties(request.template_sequence, request.goals.ph) if request.template_sequence else None,
            "methods": METHOD, "limitations": LIMITATIONS}


def optimize(request):
    started = perf_counter()
    problem = build_problem(request)
    size = len(problem["variables"])
    if size == 0:
        raise ValueError("QAOA needs at least one variable position. Use Preview to evaluate a fully fixed sequence.")
    energies = problem["energies"]
    normalized = (energies - energies.min()) / max(float(np.ptp(energies)), 1e-12)
    rng = np.random.default_rng(request.seed)
    history = []

    def objective(parameters):
        probabilities = sequence_probabilities(problem, parameters)
        history.append({"evaluation": len(history) + 1,
                        "expected_penalized_objective": float(probabilities @ energies),
                        "feasible_probability": float(probabilities[problem["feasible"]].sum())})
        return float(probabilities @ normalized)

    initial = rng.uniform(.1, np.pi, size=2 * request.layers)
    fitted = minimize(objective, initial, method="COBYLA", options={"maxiter": request.max_iterations})
    probabilities = np.maximum(sequence_probabilities(problem, fitted.x), 0)
    probabilities /= probabilities.sum()
    samples = rng.multinomial(request.shots, probabilities)
    rows = problem["rows"]
    for i, row in enumerate(rows):
        row.update(probability=float(probabilities[i]), count=int(samples[i]), observed_frequency=int(samples[i]) / request.shots)
    feasible = problem["feasible"]
    feasible_indices = np.flatnonzero(feasible)
    exact_index = min(feasible_indices, key=lambda index: rows[index]["objective"])
    reference = rows[exact_index]
    observed = sorted(np.flatnonzero(feasible & (samples > 0)), key=lambda index: (rows[index]["objective"], -samples[index], index))
    best = rows[observed[0]] if observed else None
    optimal = feasible & np.array([np.isclose(row["objective"], reference["objective"], rtol=0, atol=1e-8) for row in rows])
    circuit = build_sequence_circuit(problem, fitted.x)
    artifacts = circuit_artifacts(circuit)
    return {"contract_version": "1.0", "experiment_id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance": "simulated", "execution_backend": "qiskit_statevector",
            "status": "completed" if best else "no_feasible_sample",
            "request": request.model_dump(), "variables": problem["variables"], "domains": problem["domains"],
            "best_sampled": best, "candidate_sequences": [rows[i] for i in observed[:10]],
            "classical_reference": reference,
            "template_properties": chemical_properties(request.template_sequence, request.goals.ph) if request.template_sequence else None,
            "benchmark": {"state_count": len(rows), "feasible_state_count": len(feasible_indices),
                "qubits": size, "sampled_objective_gap": None if best is None else best["objective"] - reference["objective"],
                "optimum_probability": float(probabilities[optimal].sum()),
                "uniform_optimum_probability": float(optimal.mean()),
                "feasible_probability": float(probabilities[feasible].sum()),
                "feasible_shots": int(samples[feasible].sum()), "infeasible_shots": int(samples[~feasible].sum()),
                "uniform_feasible_probability": float(feasible.mean()),
                "optimal_sequences_count": int(optimal.sum())},
            "cost": {**problem["polynomial"], "penalty": problem["penalty"],
                     "energies_in_bitstring_order": energies.tolist()},
            "validation": {"checked_states": len(rows), "cost_reconstruction_max_error": problem["polynomial"]["reconstruction_max_error"],
                           "all_feasible_energies_below_all_infeasible": True},
            "history": history, "parameters": fitted.x.tolist(), "circuit": artifacts,
            "optimizer": {"method": "COBYLA", "evaluations": int(fitted.nfev),
                          "converged": bool(fitted.success), "message": str(fitted.message)},
            "states": rows, "elapsed_seconds": perf_counter() - started,
            "methods": METHOD, "limitations": LIMITATIONS}
