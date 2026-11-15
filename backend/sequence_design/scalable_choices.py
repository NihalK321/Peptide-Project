"""Compact categorical QAOA without a global sequence/energy table.

Only position-local tables (<=32 entries) and adjacent-position tables (<=1024)
are transformed. Pauli products assemble the exact cost algebraically.
"""

from collections import defaultdict
from itertools import product
from math import prod
from time import perf_counter
from typing import ClassVar

import numpy as np
from pydantic import Field
from qiskit import QuantumCircuit, qasm2
from scipy.optimize import minimize

from .models import MultiChoiceRequest
from .problem import chemical_properties, score_sequence


class ScalableChoiceRequest(MultiChoiceRequest):
    MAX_VARIABLE_POSITIONS: ClassVar[int] = 10
    max_iterations: int = Field(default=10, ge=10, le=30, strict=True)
    shots: int = Field(default=256, ge=128, le=1024, strict=True)
    training_shots: int = Field(default=64, ge=32, le=128, strict=True)
    bond_dimension: int = Field(default=8, ge=2, le=16, strict=True)
    classical_seconds: float = Field(default=1, ge=.1, le=5)
    # A hardware sweep is deliberately bounded and submitted in a single job.
    parameter_sets: list[list[float]] = Field(default_factory=lambda: [[1, .3], [2, .6], [3, .9]], min_length=1, max_length=8)

    def checked_parameters(self):
        if any(len(values) != 2 * self.layers or any(not np.isfinite(v) or abs(v) > 2*np.pi for v in values)
               for values in self.parameter_sets):
            raise ValueError("Each parameter set needs gamma,beta per layer, all finite and within +/-2*pi.")
        return self.parameter_sets


LIMITATIONS = [
    "This is a chemistry-descriptor optimization experiment, not a folding, binding, or biological-activity prediction.",
    "More qubits or a larger search space does not establish quantum speedup. Classical algorithms exploit structure rather than enumerating all sequences.",
    "Full hardware costs include parameter search, shots, compilation, queue/wall time and QPU usage. Sampled quality must also be compared.",
    "Dense many-qubit cost terms can require long circuits after routing; fitting within device qubit capacity does not imply useful noisy-hardware performance.",
    "Binding mutation budgets, requirements not guaranteed by fixed residues, and hydropathy ranges crossing branches are rejected, not dropped.",
    "Local MPS is approximate with bounded bond dimension; no certified simulation error is available. Large circuits can be exported even when local fitting is impractical.",
]


def local_z_expansion(table, qubits):
    """Walsh transform of a position-local diagonal table into products of Z."""
    values = np.asarray(table, dtype=float).copy()
    stride = 1
    while stride < len(values):
        for start in range(0, len(values), 2 * stride):
            a = values[start:start+stride].copy()
            b = values[start+stride:start+2*stride].copy()
            values[start:start+stride] = a+b
            values[start+stride:start+2*stride] = a-b
        stride *= 2
    values /= len(values)
    return {sum(1 << qubits[j] for j in range(len(qubits)) if (mask >> j) & 1): float(value)
            for mask, value in enumerate(values) if abs(value) > 1e-13}


def compile_choices(request):
    started = perf_counter()
    request.checked_parameters()
    domains = request.domains()
    fixed = {choices[0] for choices in domains if len(choices) == 1}
    if not set(request.required_amino_acids) <= fixed:
        raise ValueError("Guarantee each required residue at a fixed position, or use small exact mode.")
    maximum_changes = 0 if request.template_sequence is None else sum(
        any(letter != request.template_sequence[i] for letter in choices) for i, choices in enumerate(domains))
    if request.max_mutations is not None and request.max_mutations < maximum_changes:
        raise ValueError("Scalable mode requires a nonbinding mutation budget; lock positions or clear the budget.")
    baseline = ''.join(choices[0] for choices in domains)
    props = chemical_properties(baseline, request.goals.ph)
    blocks, by_position, qubits = [], {}, 0
    charge_poly, hydro_poly = {0: props["charge"]}, {0: props["hydropathy"]}
    qlow = qhigh = props["charge"]
    hlow = hhigh = props["hydropathy"]
    for position, choices in enumerate(domains):
        if len(choices) == 1:
            continue
        width = (len(choices)-1).bit_length()
        block = {"position": position+1, "choices": choices, "qubits": list(range(qubits, qubits+width)),
                 "width": width, "offset": qubits}
        qubits += width
        dq, dh = [], []
        for residue in choices:
            changed = baseline[:position]+residue+baseline[position+1:]
            values = chemical_properties(changed, request.goals.ph)
            dq.append(values["charge"]-props["charge"])
            dh.append(values["hydropathy"]-props["hydropathy"])
        block.update(charge_delta=dq, hydropathy_delta=dh)
        blocks.append(block)
        by_position[position] = block
        qlow += min(dq); qhigh += max(dq)
        hlow += min(dh); hhigh += max(dh)
        for polynomial, deltas in ((charge_poly, dq), (hydro_poly, dh)):
            table = deltas + [0.] * (2**width-len(choices))
            for mask, value in local_z_expansion(table, block["qubits"]).items():
                polynomial[mask] = polynomial.get(mask, 0) + value
    if not blocks:
        raise ValueError("Select at least one editable position.")
    goals = request.goals
    denominator = goals.charge_weight+goals.hydropathy_weight+goals.adjacent_repeat_weight
    target = None
    if goals.hydropathy_weight:
        if goals.hydropathy_min == goals.hydropathy_max:
            target = goals.hydropathy_min
        elif hlow >= goals.hydropathy_min-1e-12 and hhigh <= goals.hydropathy_max+1e-12:
            pass
        elif hlow >= goals.hydropathy_max:
            target = goals.hydropathy_max
        elif hhigh <= goals.hydropathy_min:
            target = goals.hydropathy_min
        else:
            raise ValueError("Use a hydropathy point target (minimum=maximum), zero hydropathy weight, or a range containing every choice in scalable mode.")
    terms = defaultdict(float)

    def add_square(polynomial, desired, weight):
        polynomial = dict(polynomial)
        polynomial[0] = polynomial.get(0, 0)-desired
        entries = list(polynomial.items())
        for i, (left, a) in enumerate(entries):
            for j in range(i, len(entries)):
                right, b = entries[j]
                terms[left ^ right] += weight*a*b*(1 if i == j else 2)

    add_square(charge_poly, goals.target_charge, goals.charge_weight/(4*denominator))
    if target is not None:
        add_square(hydro_poly, target, goals.hydropathy_weight/denominator)
    repeat_weight = goals.adjacent_repeat_weight/((request.length-1)*denominator)
    if repeat_weight:
        for position in range(request.length-1):
            left, right = by_position.get(position), by_position.get(position+1)
            involved = [block for block in (left, right) if block is not None]
            bits = [q for block in involved for q in block["qubits"]]
            table = []
            for index in range(2**len(bits)):
                offset, letters = 0, []
                for site, block in ((position, left), (position+1, right)):
                    if block is None:
                        letters.append(domains[site][0])
                    else:
                        code = (index >> offset) & ((1 << block["width"])-1)
                        letters.append(block["choices"][code] if code < len(block["choices"]) else block["choices"][0])
                        offset += block["width"]
                table.append(repeat_weight * (letters[0] == letters[1]))
            for mask, value in local_z_expansion(table, bits).items():
                terms[mask] += value
    # Analytic upper bound on every valid raw objective; raw cost is nonnegative.
    charge_bound = max(abs(qlow-goals.target_charge), abs(qhigh-goals.target_charge))
    hydro_bound = 0 if target is None else max(abs(hlow-target), abs(hhigh-target))
    upper_bound = (goals.charge_weight*(charge_bound/2)**2 + goals.hydropathy_weight*hydro_bound**2 + goals.adjacent_repeat_weight)/denominator
    penalty = upper_bound+1
    for block in blocks:
        invalid = [float(code >= len(block["choices"])) for code in range(2**block["width"])]
        for mask, value in local_z_expansion(invalid, block["qubits"]).items():
            terms[mask] += penalty*value
    terms = {mask: value for mask, value in terms.items() if abs(value) > 1e-12}
    scale = max(sum(abs(value) for mask, value in terms.items() if mask), 1e-12)
    gate_count = qubits + sum(2*mask.bit_count()-1 for mask in terms if mask)*request.layers + qubits*request.layers
    model = dict(domains=domains, blocks=blocks, qubits=qubits, terms=terms, scale=scale, penalty=penalty,
                 valid_objective_upper_bound=upper_bound, baseline=baseline, base_charge=props["charge"],
                 base_hydropathy=props["hydropathy"], target=target, logical_gate_count=gate_count)
    rng = np.random.default_rng(request.seed)
    states = [0, (1 << qubits)-1] + [int.from_bytes(rng.bytes(8), 'little') & ((1 << qubits)-1) for _ in range(24)]
    error = max(abs(pauli_energy(model, state)-fast_energy(model, request, state)) for state in states)
    # Also check actual chemistry on valid assignments, including varied termini.
    for _ in range(24):
        codes = [int(rng.integers(len(block["choices"]))) for block in blocks]
        state = encode_codes(model, codes)
        row = score_sequence(decode_state(model, state)[0], request)
        error = max(error, abs(row["objective"]-fast_energy(model, request, state)))
    if error > 1e-7:
        raise ValueError("Scalable local-cost/Pauli/chemistry validation failed.")
    model["validation"] = {"checked_assignments": 50, "maximum_error": error,
        "method": "Local Walsh transforms and algebraic Pauli products; deterministic/seeded checks, not exhaustive enumeration"}
    model["formulation_seconds"] = perf_counter()-started
    return model


def encode_codes(model, codes):
    return sum(int(code) << block["offset"] for code, block in zip(codes, model["blocks"]))


def decode_state(model, state):
    letters = list(model["baseline"])
    invalid = 0
    for block in model["blocks"]:
        code = (state >> block["offset"]) & ((1 << block["width"])-1)
        if code >= len(block["choices"]):
            invalid += 1
        else:
            letters[block["position"]-1] = block["choices"][code]
    return ''.join(letters), invalid


def fast_energy(model, request, state):
    charge, hydro, invalid = model["base_charge"], model["base_hydropathy"], 0
    for block in model["blocks"]:
        code = (state >> block["offset"]) & ((1 << block["width"])-1)
        if code >= len(block["choices"]):
            invalid += 1
            code = 0
        charge += block["charge_delta"][code]
        hydro += block["hydropathy_delta"][code]
    goals = request.goals
    value = goals.charge_weight*((charge-goals.target_charge)/2)**2
    if model["target"] is not None:
        value += goals.hydropathy_weight*(hydro-model["target"])**2
    if goals.adjacent_repeat_weight:
        seq = decode_state(model, state)[0]
        value += goals.adjacent_repeat_weight*sum(a == b for a, b in zip(seq, seq[1:]))/(request.length-1)
    return value/(goals.charge_weight+goals.hydropathy_weight+goals.adjacent_repeat_weight)+invalid*model["penalty"]


def pauli_energy(model, state):
    return sum(value * (-1 if (state & mask).bit_count() % 2 else 1) for mask, value in model["terms"].items())


def build_circuit(model, parameters):
    circuit = QuantumCircuit(model["qubits"])
    circuit.h(range(model["qubits"]))
    for gamma, beta in zip(parameters[::2], parameters[1::2]):
        for mask, coefficient in sorted(model["terms"].items()):
            if mask == 0:
                continue  # Constant changes only a global phase.
            bits = [i for i in range(model["qubits"]) if (mask >> i) & 1]
            for bit in bits[:-1]:
                circuit.cx(bit, bits[-1])
            circuit.rz(2*gamma*coefficient/model["scale"], bits[-1])
            for bit in reversed(bits[:-1]):
                circuit.cx(bit, bits[-1])
        circuit.rx(2*beta, range(model["qubits"]))
    return circuit


def preview_scalable(request, model=None):
    model = compile_choices(request) if model is None else model
    return {"contract_version": "2.0", "provenance": "calculated", "request": request.model_dump(),
        "qubits": model["qubits"], "editable_positions": len(model["blocks"]),
        "valid_sequence_count": str(prod(len(b["choices"]) for b in model["blocks"])),
        "encoded_state_count": str(2**model["qubits"]),
        "uniform_valid_probability": prod(len(b["choices"]) for b in model["blocks"])/(2**model["qubits"]),
        "blocks": [{k: v for k, v in b.items() if k not in ("charge_delta", "hydropathy_delta")} for b in model["blocks"]],
        "cost_terms": len(model["terms"]), "maximum_pauli_weight": max(mask.bit_count() for mask in model["terms"]),
        "logical_gate_count": model["logical_gate_count"], "formulation_seconds": model["formulation_seconds"],
        "penalty": model["penalty"], "valid_objective_upper_bound": model["valid_objective_upper_bound"],
        "validation": model["validation"], "limitations": LIMITATIONS}


def classical_search(model, request):
    """Categorical multistart descent + annealing; no binary invalid codes."""
    started = perf_counter()
    rng = np.random.default_rng(request.seed)
    domains = [len(block["choices"]) for block in model["blocks"]]
    evaluations, best, best_codes, trace = 0, float('inf'), None, []

    def evaluate(codes):
        nonlocal evaluations, best, best_codes
        value = fast_energy(model, request, encode_codes(model, codes))
        evaluations += 1
        if value < best-1e-12:
            best, best_codes = value, list(codes)
            trace.append({"evaluation": evaluations, "seconds": perf_counter()-started, "objective": best})
        return value

    size = prod(domains)
    exact = size <= 4096
    if exact:
        for codes in product(*(range(n) for n in domains)):
            evaluate(codes)
    else:
        # Spend the stated wall-clock budget on valid categorical moves, never 2^n enumeration.
        while best_codes is None or perf_counter()-started < request.classical_seconds:
            codes = [int(rng.integers(n)) for n in domains]
            current = evaluate(codes)
            for _ in range(10):
                improved = False
                for i in rng.permutation(len(domains)):
                    original, chosen, local = codes[i], codes[i], current
                    for code in range(domains[i]):
                        codes[i] = code
                        value = evaluate(codes)
                        if value < local-1e-12:
                            chosen, local, improved = code, value, True
                    codes[i], current = chosen, local
                    if perf_counter()-started >= request.classical_seconds:
                        break
                if not improved or perf_counter()-started >= request.classical_seconds:
                    break
            for step in range(100):
                if perf_counter()-started >= request.classical_seconds:
                    break
                proposal = codes.copy()
                for i in rng.choice(len(domains), size=min(2, len(domains)), replace=False):
                    proposal[i] = int(rng.integers(domains[i]))
                value = evaluate(proposal)
                temperature = max(.001, .2*(1-step/100))
                if value < current or rng.random() < np.exp(min(0, (current-value)/temperature)):
                    codes, current = proposal, value
    row = score_sequence(decode_state(model, encode_codes(model, best_codes))[0], request)
    return {"best": row, "method": "exact categorical enumeration" if exact else "time-bounded multistart categorical coordinate descent plus two-position simulated annealing",
        "exact_optimum_available": exact, "evaluations": evaluations, "elapsed_seconds": perf_counter()-started,
        "budget_seconds": request.classical_seconds, "seed": request.seed, "history": trace}


def summarize_counts(model, request, counts):
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("No measurement shots returned.")
    observed, invalid_shots = [], 0
    for bits, count in counts.items():
        if len(bits) != model["qubits"] or set(bits)-{'0', '1'} or count <= 0:
            raise ValueError("Unexpected measurement bitstring or count.")
        sequence, invalid = decode_state(model, int(bits, 2))
        if invalid:
            invalid_shots += count
            continue
        row = score_sequence(sequence, request)
        if not row["feasible"]:
            raise ValueError("A decoded sequence violated an encoding-enforced constraint.")
        observed.append({**row, "bitstring": bits, "count": count, "observed_frequency": count/total})
    observed.sort(key=lambda row: (row["objective"], -row["count"]))
    return {"best_sampled": observed[0] if observed else None, "candidate_sequences": observed[:10],
        "shots": total, "feasible_shots": total-invalid_shots, "invalid_shots": invalid_shots,
        "observed_feasible_frequency": (total-invalid_shots)/total,
        "sampled_expected_penalized_cost": sum(fast_energy(model, request, int(bits, 2))*n for bits, n in counts.items())/total}


def reference_quality(model, request, counts, classical):
    """Finite-shot frequency of reaching the same independently computed target."""
    threshold = classical['best']['objective']
    successes = sum(count for bits, count in counts.items()
        if not decode_state(model, int(bits, 2))[1] and fast_energy(model, request, int(bits, 2)) <= threshold+1e-8)
    shots = sum(counts.values())
    p, z = successes/shots, 1.96
    denominator = 1+z*z/shots
    center = (p+z*z/(2*shots))/denominator
    radius = z*np.sqrt(p*(1-p)/shots+z*z/(4*shots*shots))/denominator
    return {'target_objective': threshold, 'target_is_exact_optimum': classical['exact_optimum_available'],
        'matched_or_better_shots': successes, 'total_shots': shots, 'observed_frequency': p,
        'wilson_95_interval': [max(0., float(center-radius)), min(1., float(center+radius))],
        'interval_assumption': 'Binomial independent shots; hardware drift/correlation and parameter-selection bias are not modeled.'}


def sample_local(model, request, parameters, shots, seed):
    if model["logical_gate_count"] > 15000:
        raise ValueError("This circuit exceeds the bounded local simulation budget (15,000 logical gates). Reduce choices/positions, or prepare a QPU circuit for inspection.")
    from qiskit_aer import AerSimulator
    circuit = build_circuit(model, parameters)
    circuit.measure_all()
    simulator = AerSimulator(method="matrix_product_state", max_memory_mb=256, max_parallel_threads=2,
        matrix_product_state_max_bond_dimension=request.bond_dimension,
        matrix_product_state_truncation_threshold=1e-10, mps_sample_measure_algorithm="mps_apply_measure", fusion_enable=False)
    result = simulator.run(circuit, shots=shots, seed_simulator=seed).result()
    if not result.success:
        raise ValueError("Bounded local MPS simulation failed.")
    return {bits.replace(' ', ''): int(count) for bits, count in result.get_counts().items()}


def run_scalable(request, export_only=False):
    started = perf_counter()
    model = compile_choices(request)
    parameters = np.array(request.parameter_sets[0], dtype=float)
    history, summary, fitted = [], None, None
    if not export_only:
        def objective(values):
            counts = sample_local(model, request, values, request.training_shots, request.seed)
            row = summarize_counts(model, request, counts)
            history.append({"evaluation": len(history)+1, "expected_penalized_cost": row["sampled_expected_penalized_cost"],
                            "feasible_frequency": row["observed_feasible_frequency"]})
            return row["sampled_expected_penalized_cost"]/model["scale"]
        fitted = minimize(objective, parameters, method="COBYLA", options={"maxiter": request.max_iterations})
        parameters = fitted.x
        counts = sample_local(model, request, parameters, request.shots, request.seed+1)
        summary = summarize_counts(model, request, counts)
    quantum_seconds = perf_counter()-started-model["formulation_seconds"]
    baseline = classical_search(model, request)
    if summary is not None:
        summary['reference_quality'] = reference_quality(model, request, counts, baseline)
    circuit = build_circuit(model, parameters)
    return {**preview_scalable(request, model), "provenance": "prepared" if export_only else "simulated_approximate",
        "execution_backend": "not_executed" if export_only else "qiskit_aer_mps", "parameters": parameters.tolist(),
        "history": history, "summary": summary, "classical": baseline,
        "circuit": {"qasm": qasm2.dumps(circuit), "depth": circuit.depth(), "gate_counts": dict(circuit.count_ops())},
        "quantum_workflow_seconds": None if export_only else quantum_seconds,
        "optimizer_evaluations": None if fitted is None else int(fitted.nfev),
        "optimizer": None if fitted is None else {'method': 'COBYLA', 'converged': bool(fitted.success), 'message': str(fitted.message)},
        "simulator": None if export_only else {"method": "matrix_product_state", "max_bond_dimension": request.bond_dimension,
            "truncation_threshold": 1e-10, "training_shots": request.training_shots, "seed": request.seed, "certified_error_bound": None},
        "comparison": "Local quantum simulation and classical search used different budgets. Compare objective quality and time together; no speedup ratio is inferred.",
        "elapsed_seconds": perf_counter()-started}
