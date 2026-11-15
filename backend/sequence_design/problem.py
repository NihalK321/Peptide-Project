"""Documented chemistry, exact restricted state space, and cost representation."""

from functools import lru_cache
import numpy as np
from ..peptide_analysis import analyze_sequence


LIMITATIONS = [
    "Proposed sequences are research candidates, not experimentally validated peptides or medicines.",
    "Charge, pI, mass and GRAVY use the existing Biopython sequence-analysis interface for linear unmodified peptides with free termini.",
    "pH describes the surrounding solution; target charge at that pH is not a target peptide pH or a pI target.",
    "Composition-based objectives may tie for different residue orders; only the optional adjacent-repeat preference explicitly distinguishes local order.",
    "The repeat term is a researcher-defined sequence-pattern preference, not a stability, folding, binding or activity prediction.",
    "The bounded space is fully enumerated classically to construct and validate the cost and exact baseline. No quantum speedup is claimed.",
    "Higher-order constraints are represented exactly by a diagonal cost Hamiltonian, not mislabeled as a quadratic QUBO.",
    "QAOA uses ideal statevector simulation and simulated shot counts; no IBM hardware job is submitted.",
    "2-50 total residues and at most eight binary variable positions are software prototype limits, not hardware capabilities.",
]


@lru_cache(maxsize=20000)
def chemical_properties(sequence, ph):
    analysis = analyze_sequence(sequence, target_ph=ph)
    if not analysis.is_calculated:
        raise ValueError("The chemistry interface cannot calculate this sequence.")
    return {"length": analysis.sequence_length, "charge": analysis.estimated_net_charge,
            "hydropathy": analysis.average_kyte_doolittle_hydropathy,
            "mass_da": analysis.molecular_mass_da, "isoelectric_point": analysis.estimated_isoelectric_point}


def score_sequence(sequence, request):
    properties = chemical_properties(sequence, request.goals.ph)
    goals = request.goals
    charge_error = properties["charge"] - goals.target_charge
    hydropathy_distance = max(goals.hydropathy_min - properties["hydropathy"], 0, properties["hydropathy"] - goals.hydropathy_max)
    adjacent_repeats = sum(first == second for first, second in zip(sequence, sequence[1:]))
    components = {"charge": goals.charge_weight * (charge_error / 2) ** 2,
                  "hydropathy": goals.hydropathy_weight * hydropathy_distance ** 2,
                  "adjacent_repeats": goals.adjacent_repeat_weight * adjacent_repeats / (len(sequence) - 1)}
    denominator = goals.charge_weight + goals.hydropathy_weight + goals.adjacent_repeat_weight
    objective = sum(components.values()) / denominator
    mutations = None if request.template_sequence is None else sum(a != b for a, b in zip(sequence, request.template_sequence))
    missing = sorted(set(request.required_amino_acids) - set(sequence))
    excess = 0 if request.max_mutations is None else max(0, mutations - request.max_mutations)
    return {"sequence": sequence, "properties": properties, "objective": float(objective),
            "components": components, "component_weight_sum": denominator,
            "charge_error_e": charge_error, "hydropathy_distance": hydropathy_distance,
            "adjacent_repeat_count": adjacent_repeats, "mutation_count": mutations,
            "missing_required_amino_acids": missing, "mutation_budget_excess": excess,
            "constraint_violation": len(missing) + excess ** 2, "feasible": not missing and excess == 0}


def binary_polynomial(energies):
    """Exact Boolean Möbius transform; report quadratic only after checking it."""
    coefficients = np.array(energies, dtype=float).copy()
    size = (len(coefficients)).bit_length() - 1
    for bit in range(size):
        for index in range(len(coefficients)):
            if (index >> bit) & 1:
                coefficients[index] -= coefficients[index ^ (1 << bit)]
    terms = [{"mask": index, "variables": [i for i in range(size) if (index >> i) & 1], "coefficient": float(value)}
             for index, value in enumerate(coefficients) if abs(value) > 1e-8]
    degree = max((len(term["variables"]) for term in terms), default=0)
    reconstruction = np.array([sum(term["coefficient"] for term in terms if (index & term["mask"]) == term["mask"])
                               for index in range(len(energies))])
    error = float(np.max(np.abs(reconstruction - energies)))
    if error > 1e-6:
        raise ValueError("Cost polynomial reconstruction failed.")
    quadratic = None
    if degree <= 2:
        linear = [float(coefficients[1 << i]) for i in range(size)]
        matrix = np.zeros((size, size))
        np.fill_diagonal(matrix, linear)
        for i in range(size):
            for j in range(i + 1, size):
                matrix[i, j] = coefficients[(1 << i) | (1 << j)]
        quadratic = {"constant": float(coefficients[0]), "matrix_upper_triangle": matrix.tolist(),
                     "convention": "constant + x.T @ Q_upper @ x; each pair counted once"}
    return {"degree": degree, "terms": terms, "reconstruction_max_error": error, "qubo": quadratic,
            "representation": "quadratic_qubo" if quadratic is not None else "higher_order_diagonal"}


def build_problem(request):
    domains = request.domains()
    variable_positions = [index for index, choices in enumerate(domains) if len(choices) == 2]
    variable_lookup = {position: bit for bit, position in enumerate(variable_positions)}
    rows = []
    for state in range(2 ** len(variable_positions)):
        sequence = ''.join(choices[(state >> variable_lookup[position]) & 1] if position in variable_lookup else choices[0]
                           for position, choices in enumerate(domains))
        rows.append({"bitstring": format(state, f"0{len(variable_positions)}b") if variable_positions else "",
                     **score_sequence(sequence, request)})
    if not any(row["feasible"] for row in rows):
        raise ValueError("No sequence satisfies all required amino acids and the mutation budget in this space. Relax those constraints or change position choices.")
    raw = np.array([row["objective"] for row in rows])
    penalty = float(np.ptp(raw) + 1)
    energies = np.array([row["objective"] + penalty * row["constraint_violation"] for row in rows])
    for row, energy in zip(rows, energies):
        row["penalized_objective"] = float(energy)
    feasible = np.array([row["feasible"] for row in rows])
    if np.any(~feasible) and not energies[~feasible].min() > energies[feasible].max():
        raise ValueError("Cardinality/required-residue penalty separation failed.")
    return {"domains": domains, "variables": [{"qubit": bit, "position": position + 1, "choices": domains[position]} for bit, position in enumerate(variable_positions)],
            "rows": rows, "energies": energies, "feasible": feasible, "penalty": penalty,
            "polynomial": binary_polynomial(energies)}
