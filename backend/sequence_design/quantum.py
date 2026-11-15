"""Use the existing native QAOA circuit for QUBOs; exact diagonal cost otherwise."""

import numpy as np
from qiskit import QuantumCircuit, qasm2
from qiskit.circuit.library import DiagonalGate, RXGate
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
    if any(len(block["choices"]) > 2 for block in problem.get("encoding_blocks", [])):
        # Apply the diagonal unitary directly to amplitudes, avoiding repeated
        # synthesis of thousands of elementary gates during parameter fitting.
        # This is the same ideal QAOA circuit, checked against Qiskit's circuit.
        energies = problem["energies"]
        normalized = (energies - energies.min()) / max(float(np.ptp(energies)), 1e-12)
        size = len(problem["variables"])
        state = Statevector(np.ones(len(energies), dtype=complex) / np.sqrt(len(energies)))
        for gamma, beta in np.asarray(parameters).reshape(-1, 2):
            state = Statevector(state.data * np.exp(-1j * gamma * normalized))
            for bit in range(size):
                state = state.evolve(RXGate(2 * beta), [bit])
        return state.probabilities()
    return Statevector.from_instruction(build_sequence_circuit(problem, parameters)).probabilities()


def circuit_artifacts(circuit):
    return {"qasm": qasm2.dumps(_expand_for_display(circuit)),
            "text": (f"{circuit.num_qubits}-qubit QAOA circuit: H on each qubit, followed by alternating exact diagonal cost and RX mixer layers. Full elementary-gate circuit is available in the OpenQASM download."
                     if circuit.num_qubits > 8 else str(circuit.draw(output="text", fold=100))),
            "depth": circuit.depth(), "gate_counts": dict(circuit.count_ops())}
