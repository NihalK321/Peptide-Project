"""Analytical quadratic sequence costs: O(n²), without enumerating 2**n states.

This path deliberately accepts only objectives/constraints representable by the
quadratic model. Unsupported range/required-residue/budget terms are rejected,
never dropped or replaced silently.
"""

import numpy as np

from .problem import chemical_properties, score_sequence
from ..blends.quantum import qubo_to_ising, build_blend_circuit


def decode(domains, variables, bits):
    positions = {row["position"] - 1: row["qubit"] for row in variables}
    return ''.join(choices[int(bits[positions[i]])] if i in positions else choices[0] for i, choices in enumerate(domains))


def compile_quadratic(request):
    domains = request.domains()
    variables = [{"qubit": i, "position": position + 1, "choices": choices}
                 for i, (position, choices) in enumerate((index, row) for index, row in enumerate(domains) if len(row) == 2)]
    size = len(variables)
    fixed = {row[0] for row in domains if len(row) == 1}
    if not set(request.required_amino_acids) <= fixed:
        raise ValueError("Large-circuit mode requires each required residue to be guaranteed by a fixed position. Lock it into the sequence or clear that requirement; it will not be silently ignored.")
    maximum_changes = None if request.template_sequence is None else sum(any(letter != request.template_sequence[i] for letter in choices) for i, choices in enumerate(domains))
    if request.max_mutations is not None and request.max_mutations < maximum_changes:
        raise ValueError("Large-circuit mode does not support a binding mutation budget. Clear the budget, use fixed positions, or use the exact small-instance mode.")
    baseline = ''.join(row[0] for row in domains)
    props = chemical_properties(baseline, request.goals.ph)
    charge_delta, hydro_delta = np.zeros(size), np.zeros(size)
    for variable in variables:
        letters = list(baseline)
        letters[variable["position"] - 1] = variable["choices"][1]
        changed = chemical_properties(''.join(letters), request.goals.ph)
        charge_delta[variable["qubit"]] = changed["charge"] - props["charge"]
        hydro_delta[variable["qubit"]] = changed["hydropathy"] - props["hydropathy"]
    goals = request.goals
    total_weight = goals.charge_weight + goals.hydropathy_weight + goals.adjacent_repeat_weight
    constant = 0.0
    linear = np.zeros(size)
    pairs = np.zeros((size, size))

    def add_square(base, delta, weight):
        nonlocal constant
        constant += weight * base ** 2
        linear[:] += weight * (2 * base * delta + delta ** 2)
        pairs[:] += np.triu(2 * weight * np.outer(delta, delta), 1)

    add_square(props["charge"] - goals.target_charge, charge_delta, goals.charge_weight / (4 * total_weight))
    hydro_minimum = props["hydropathy"] + float(np.minimum(hydro_delta, 0).sum())
    hydro_maximum = props["hydropathy"] + float(np.maximum(hydro_delta, 0).sum())
    hydro_branch = "disabled"
    if goals.hydropathy_weight:
        if goals.hydropathy_min == goals.hydropathy_max:
            target = goals.hydropathy_min
            hydro_branch = "point_target"
        elif hydro_minimum >= goals.hydropathy_min - 1e-12 and hydro_maximum <= goals.hydropathy_max + 1e-12:
            target = None
            hydro_branch = "entire_space_inside_range"
        elif hydro_minimum >= goals.hydropathy_max:
            target = goals.hydropathy_max
            hydro_branch = "entire_space_above_range"
        elif hydro_maximum <= goals.hydropathy_min:
            target = goals.hydropathy_min
            hydro_branch = "entire_space_below_range"
        else:
            raise ValueError("This hydropathy range crosses cost branches and is not a quadratic objective. In large mode use a point target (minimum=maximum), zero hydropathy weight, or a range containing the entire allowed space. Small exact mode preserves arbitrary ranges.")
        if target is not None:
            add_square(props["hydropathy"] - target, hydro_delta, goals.hydropathy_weight / total_weight)
    by_position = {row["position"] - 1: row["qubit"] for row in variables}
    repeat_weight = goals.adjacent_repeat_weight / ((request.length - 1) * total_weight)
    for pos in range(request.length - 1):
        left, right = domains[pos], domains[pos + 1]
        f00 = float(left[0] == right[0]) * repeat_weight
        constant += f00
        i, j = by_position.get(pos), by_position.get(pos + 1)
        if i is not None:
            linear[i] += float(left[1] == right[0]) * repeat_weight - f00
        if j is not None:
            linear[j] += float(left[0] == right[1]) * repeat_weight - f00
        if i is not None and j is not None:
            pairs[i, j] += (float(left[1] == right[1]) - float(left[1] == right[0]) - float(left[0] == right[1]) + float(left[0] == right[0])) * repeat_weight
    offset, fields, couplings = qubo_to_ising(constant, linear, pairs)
    # Bound the full nonconstant cost range without generating an energy table.
    scale = max(float(np.abs(linear).sum() + np.abs(pairs).sum()), 1e-12)
    rng = np.random.default_rng(request.seed)
    checks = [np.zeros(size, dtype=int), np.ones(size, dtype=int)]
    checks.extend(rng.integers(0, 2, size=size) for _ in range(32))
    errors, charge_errors = [], []
    for bits in checks:
        row = score_sequence(decode(domains, variables, bits), request)
        value = constant + linear @ bits + bits @ pairs @ bits
        z = 1 - 2 * bits
        ising_value = offset + fields @ z + z @ couplings @ z
        errors.extend([abs(value-row["objective"]), abs(value-ising_value)])
        charge_errors.append(abs(row["properties"]["charge"] - (props["charge"] + charge_delta @ bits)))
    if max(errors + charge_errors, default=0) > 1e-7:
        raise ValueError("Analytical QUBO/chemistry/Ising validation failed.")
    return {"domains": domains, "variables": variables, "constant": float(constant),
            "linear": linear, "quadratic": pairs, "offset": offset, "fields": fields,
            "couplings": couplings, "scale": scale, "hydropathy_branch": hydro_branch,
            "validation": {"method": "analytical coefficient construction plus deterministic and seeded assignment checks; not exhaustive",
                           "checked_assignments": len(checks), "maximum_error": float(max(errors, default=0)),
                           "maximum_charge_affinity_error": float(max(charge_errors, default=0))}}


def objective_value(model, bits):
    bits = np.asarray(bits, dtype=float)
    return float(model["constant"] + model["linear"] @ bits + bits @ model["quadratic"] @ bits)


def scalable_circuit(model, parameters):
    return build_blend_circuit(model["fields"], model["couplings"], parameters, model["scale"])
