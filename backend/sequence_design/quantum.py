"""Use the existing native QAOA circuit for QUBOs; exact diagonal cost otherwise."""

import numpy as np
from qiskit import QuantumCircuit, qasm2
from qiskit.circuit.library import DiagonalGate
from qiskit.quantum_info import Statevector
from ..blends.quantum import build_blend_circuit, qubo_to_ising
from ..quantum import _expand_for_display


def build_sequence_circuit(problem, parameters):
    energies = problem["energies"]
    size = len(problem["variables"])
    scale = max(float(np.ptp(energies)), 1e-12)
    qubo = problem["polynomial"]["qubo"]
    if qubo is not None:
        matrix = np.array(qubo["matrix_upper_triangle"])
        _, fields, couplings = qubo_to_ising(qubo["constant"], np.diag(matrix), np.triu(matrix, 1))
        return build_blend_circuit(fields, couplings, parameters, scale)
    # Exact higher-order cost is important for required-residue and range terms.
    # No higher-order term is silently discarded to force this into a QUBO.
    circuit = QuantumCircuit(size)
    circuit.h(range(size))
    normalized = (energies - energies.min()) / scale
    for gamma, beta in np.asarray(parameters).reshape(-1, 2):
        circuit.append(DiagonalGate(np.exp(-1j * gamma * normalized)), range(size))
        circuit.rx(2 * beta, range(size))
    return circuit


def sequence_probabilities(problem, parameters):
    return Statevector.from_instruction(build_sequence_circuit(problem, parameters)).probabilities()


def circuit_artifacts(circuit):
    return {"qasm": qasm2.dumps(_expand_for_display(circuit)),
            "text": str(circuit.draw(output="text", fold=100)),
            "depth": circuit.depth(), "gate_counts": dict(circuit.count_ops())}
