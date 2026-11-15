"""Bounded MPS sampling and circuit preparation without exponential tables."""

from datetime import datetime, timezone
from importlib.metadata import version
from time import perf_counter
from uuid import uuid4

import numpy as np
from scipy.optimize import minimize

from .problem import chemical_properties, score_sequence
from qiskit import qasm2
from ..quantum import _expand_for_display
from .scalable import compile_quadratic, decode, objective_value, scalable_circuit
from .solver import METHOD


LIMITATIONS = [
    "This large-mode objective is an analytically constructed QUBO; no full 2^n state space or dense statevector is generated.",
    "Required residues must be guaranteed by fixed positions; binding mutation budgets and hydropathy ranges crossing cost branches are rejected, not ignored.",
    "MPS simulation has a finite bond-dimension cap and truncation threshold. It is approximate, may lose accuracy with entanglement, and has no certified global error bound here.",
    "Reported frequencies come from finite simulated shots, not exact probabilities or real IBM hardware.",
    "The classical comparison is bounded coordinate-descent heuristic search. It is not an exact optimum, optimality gap, or proof of quantum advantage.",
    "Charge and hydropathy are sequence-derived models for linear unmodified free-termini chains, not predictions of folding, binding, efficacy or biological function.",
]


def preview_large(request):
    model = compile_quadratic(request)
    size = len(model["variables"])
    return {"contract_version": "1.1", "provenance": "calculated", "request": request.model_dump(),
            "variables": model["variables"], "domains": model["domains"], "qubits": size,
            "state_count": 2 ** size, "feasible_state_count": 2 ** size,
            "cost_representation": "analytical_qubo_no_enumeration", "cost_polynomial_degree": 2 if np.any(np.abs(model["quadratic"]) > 1e-12) else (1 if np.any(np.abs(model["linear"]) > 1e-12) else 0),
            "template_properties": chemical_properties(request.template_sequence, request.goals.ph) if request.template_sequence else None,
            "validation": model["validation"], "methods": {**METHOD,
                "constraints": "Accepted requirements are guaranteed by fixed positions or proven nonbinding; unsupported constraints are rejected",
                "penalty": "No penalty needed: all encoded states satisfy the accepted hard constraints",
                "cost_construction": "Analytical QUBO from affine charge/GRAVY and neighboring-repeat terms; no exhaustive table"}, "limitations": LIMITATIONS}


def classical_heuristic(model, seed):
    """A bounded baseline only; never present this as the exact global optimum."""
    size = len(model["variables"])
    rng = np.random.default_rng(seed)
    starts = [np.zeros(size, dtype=int), np.ones(size, dtype=int)] + [rng.integers(0, 2, size) for _ in range(4)]
    best_bits, best = starts[0], float("inf")
    evaluations = 0
    for start in starts:
        bits = start.copy()
        current = objective_value(model, bits)
        for _ in range(20):
            improved = False
            for i in rng.permutation(size):
                bits[i] ^= 1
                value = objective_value(model, bits)
                evaluations += 1
                if value < current - 1e-12:
                    current = value
                    improved = True
                else:
                    bits[i] ^= 1
            if not improved:
                break
        if current < best:
            best, best_bits = current, bits.copy()
    return best_bits, evaluations


def sample_mps(model, parameters, shots, seed, bond_dimension):
    try:
        from qiskit_aer import AerSimulator
    except ImportError as error:
        raise ValueError("Large local runs require qiskit-aer. Install backend/sequence_design/requirements-large.txt, or choose circuit preparation only.") from error
    simulator = AerSimulator(method="matrix_product_state", max_memory_mb=256, max_parallel_threads=2,
        matrix_product_state_max_bond_dimension=bond_dimension,
        matrix_product_state_truncation_threshold=1e-10,
        mps_sample_measure_algorithm="mps_apply_measure", fusion_enable=False)
    circuit = scalable_circuit(model, parameters)
    circuit.measure_all()
    # Explicit gate expansion avoids generic hardware plugin/transpiler loading.
    # Aer supports h/rz/rx/cx; RZZ(a) is expanded into CX/RZ(a)/CX.
    from qiskit import QuantumCircuit
    native = QuantumCircuit(circuit.num_qubits, circuit.num_clbits)
    for instruction in circuit.data:
        qubits = [circuit.find_bit(q).index for q in instruction.qubits]
        clbits = [circuit.find_bit(c).index for c in instruction.clbits]
        if instruction.operation.name == "rzz":
            native.cx(*qubits); native.rz(instruction.operation.params[0], qubits[1]); native.cx(*qubits)
        else:
            native.append(instruction.operation, qubits, clbits)
    result = simulator.run(native, shots=shots, seed_simulator=seed).result()
    if not result.success:
        raise ValueError(f"Bounded MPS simulation failed: {result.status}")
    return {bits.replace(' ', ''): int(count) for bits, count in result.get_counts().items()}


def run_large(request, export_only=False):
    started = perf_counter()
    model = compile_quadratic(request)
    formulation_seconds = perf_counter() - started
    size = len(model["variables"])
    if size == 0:
        raise ValueError("At least one variable position is required for a large circuit.")
    initial = np.tile([request.initial_gamma, request.initial_beta], request.layers)
    history = []

    def sampled_objective(parameters):
        counts = sample_mps(model, parameters, request.training_shots, request.seed, request.mps_bond_dimension)
        average = sum(objective_value(model, [int(bit) for bit in bits[::-1]]) * count for bits, count in counts.items()) / request.training_shots
        history.append({"evaluation": len(history) + 1, "sampled_expected_objective": average})
        return average / model["scale"]

    execution_started = perf_counter()
    fitted = None if export_only else minimize(sampled_objective, initial, method="COBYLA", options={"maxiter": request.max_iterations})
    parameters = initial if fitted is None else fitted.x
    counts = {} if export_only else sample_mps(model, parameters, request.shots, request.seed + 1, request.mps_bond_dimension)
    execution_seconds = None if export_only else perf_counter() - execution_started
    observed = []
    for bits, count in counts.items():
        row = score_sequence(decode(model["domains"], model["variables"], [int(bit) for bit in bits[::-1]]), request)
        if not row["feasible"]:
            raise ValueError("A large-mode sample violated a supposedly encoding-enforced constraint.")
        observed.append({**row, "bitstring": bits, "count": count, "observed_frequency": count / request.shots})
    observed.sort(key=lambda row: (row["objective"], -row["count"], row["bitstring"]))
    classical_started = perf_counter()
    baseline_bits, baseline_evaluations = classical_heuristic(model, request.seed)
    classical_seconds = perf_counter() - classical_started
    baseline = score_sequence(decode(model["domains"], model["variables"], baseline_bits), request)
    baseline["method"] = "Six-start, up-to-20-sweep binary coordinate descent; no optimality certificate"
    baseline["evaluations"] = baseline_evaluations
    circuit = scalable_circuit(model, parameters)
    export_started = perf_counter()
    # A folded 50-qubit text drawing can be megabytes. Keep the full executable
    # circuit in QASM and return a clearly labeled summary for browser storage.
    artifacts = {"qasm": qasm2.dumps(_expand_for_display(circuit)),
        "text": f"Circuit summary only: {size} qubits, {request.layers} QAOA layer(s). H preparation, RZ/RZZ cost, RX mixing. Download QASM for every gate and fitted angle.",
        "depth": circuit.depth(), "gate_counts": dict(circuit.count_ops())}
    export_seconds = perf_counter() - export_started
    return {"contract_version": "1.1", "experiment_id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "circuit_prepared" if export_only else "completed", "provenance": "prepared" if export_only else "simulated_approximate",
        "execution_backend": "not_executed" if export_only else "qiskit_aer_mps", "request": request.model_dump(),
        "variables": model["variables"], "qubits": size, "state_space_size": 2 ** size,
        "best_sampled": observed[0] if observed else None, "candidate_sequences": observed[:10],
        "classical_baseline": baseline, "exact_optimum_available": False, "optimality_gap": None,
        "sampled_minus_heuristic_objective": None if not observed else observed[0]["objective"] - baseline["objective"],
        "counts": counts, "shots": 0 if export_only else request.shots, "history": history,
        "parameters": parameters.tolist(), "circuit": artifacts,
        "qubo": {"constant": model["constant"], "matrix_upper_triangle": (model["quadratic"] + np.diag(model["linear"])).tolist(), "convention": "constant+x.T@Q_upper@x; pairs counted once"},
        "ising": {"offset": model["offset"], "fields": model["fields"].tolist(), "couplings_upper_triangle": model["couplings"].tolist(), "energy_scale": model["scale"]},
        "validation": model["validation"], "optimizer": None if fitted is None else {"evaluations": int(fitted.nfev), "converged": bool(fitted.success), "message": str(fitted.message)},
        "simulator": None if export_only else {"version": version("qiskit-aer"), "method": "matrix_product_state", "max_bond_dimension": request.mps_bond_dimension,
            "truncation_threshold": 1e-10, "training_shots": request.training_shots, "training_seed": request.seed,
            "final_sampling_seed": request.seed + 1, "sample_algorithm": "mps_apply_measure", "certified_error_bound": None},
        "timings": {"formulation_seconds": formulation_seconds, "qaoa_simulation_fit_and_sampling_seconds": execution_seconds,
            "classical_heuristic_seconds": classical_seconds, "circuit_export_seconds": export_seconds,
            "comparison_context": "Both solvers ran classically on this computer. Different evaluation budgets and solution quality; this is not a QPU-versus-classical speedup measurement."},
        "elapsed_seconds": perf_counter()-started, "limitations": LIMITATIONS}
