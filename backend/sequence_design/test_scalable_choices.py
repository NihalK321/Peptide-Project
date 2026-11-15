"""New algebraic compact encoding: exact small checks, bounded large runs."""

from itertools import product
from math import prod

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from qiskit import qasm2
from qiskit.quantum_info import Statevector

from backend.api import app
from backend.schema import STANDARD_AMINO_ACIDS
from .problem import score_sequence
from .scalable_choices import (ScalableChoiceRequest, build_circuit, classical_search,
    compile_choices, decode_state, encode_codes, fast_energy, local_z_expansion,
    pauli_energy, preview_scalable, run_scalable, sample_local, summarize_counts)


def config(choices='AKR', length=2):
    return dict(length=length, template_sequence='A'*length,
        positions=[dict(position=i+1, choices=list(choices)) for i in range(length)],
        goals=dict(hydropathy_min=0, hydropathy_max=0, adjacent_repeat_weight=.3),
        shots=128, training_shots=32, max_iterations=10, classical_seconds=.1)


def test_local_walsh_transform():
    table = [3, 0, 2, 1, -1, 4, 2, 3]
    terms = local_z_expansion(table, [1, 3, 5])
    for code, expected in enumerate(table):
        state = sum(((code >> i) & 1) << q for i, q in enumerate([1, 3, 5]))
        assert sum(value*(-1 if (state & mask).bit_count()%2 else 1) for mask, value in terms.items()) == expected


@pytest.mark.parametrize('choices', ['AK', 'AKR', 'ACDE', 'ACDEG'])
def test_all_small_states_chemistry_pauli_unused_codes(choices):
    request = ScalableChoiceRequest(**config(choices))
    model = compile_choices(request)
    feasible, invalid = [], []
    for state in range(2**model['qubits']):
        sequence, invalid_count = decode_state(model, state)
        expected = score_sequence(sequence, request)['objective'] + invalid_count*model['penalty']
        assert fast_energy(model, request, state) == pytest.approx(expected, abs=1e-10)
        assert pauli_energy(model, state) == pytest.approx(expected, abs=1e-10)
        (invalid if invalid_count else feasible).append(expected)
    if invalid:
        assert min(invalid) > max(feasible)
    assert model['logical_gate_count'] == sum(build_circuit(model, [1, .5]).count_ops().values())


def test_fifty_qubits_no_global_enumeration(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Global enumeration must not occur in compilation')
    monkeypatch.setattr('backend.sequence_design.scalable_choices.product', forbidden)
    monkeypatch.setattr('backend.sequence_design.problem.build_problem', forbidden)
    report = preview_scalable(ScalableChoiceRequest(**config(STANDARD_AMINO_ACIDS, 10)))
    assert report['qubits'] == 50
    assert report['valid_sequence_count'] == '10240000000000'
    assert report['encoded_state_count'] == str(2**50)
    assert report['validation']['maximum_error'] < 1e-7
    assert report['logical_gate_count'] > 15000
    assert report['maximum_pauli_weight'] <= 10


def test_exact_cost_circuit_agrees_with_diagonal_evolution():
    request = ScalableChoiceRequest(**config())
    model = compile_choices(request)
    parameters = [1.2, .4, 2.1, .7]
    circuit = build_circuit(model, parameters)
    energies = np.array([fast_energy(model, request, i) for i in range(2**model['qubits'])])
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import DiagonalGate
    direct = QuantumCircuit(model['qubits'])
    direct.h(range(model['qubits']))
    for gamma, beta in zip(parameters[::2], parameters[1::2]):
        direct.append(DiagonalGate(np.exp(-1j*gamma*energies/model['scale'])), range(model['qubits']))
        direct.rx(2*beta, range(model['qubits']))
    np.testing.assert_allclose(Statevector.from_instruction(circuit).probabilities(),
                               Statevector.from_instruction(direct).probabilities(), atol=1e-12)


def test_fixed_sites_termini_requirements_and_nonbinding_budget():
    values = config('ACDE', 4)
    values.update(positions=[dict(position=1, choices=list('APD')), dict(position=4, choices=list('AKR'))],
                  required_amino_acids=['A'], max_mutations=2)
    request = ScalableChoiceRequest(**values)
    model = compile_choices(request)
    for codes in product(range(3), repeat=2):
        state = encode_codes(model, codes)
        sequence, invalid = decode_state(model, state)
        assert not invalid and sequence[1:3] == 'AA'
        assert fast_energy(model, request, state) == pytest.approx(score_sequence(sequence, request)['objective'])
    values['max_mutations'] = 1
    with pytest.raises(ValueError, match='budget'):
        compile_choices(ScalableChoiceRequest(**values))
    values.update(max_mutations=None, required_amino_acids=['P'])
    with pytest.raises(ValueError, match='fixed'):
        compile_choices(ScalableChoiceRequest(**values))


def test_unsupported_ranges_bad_angles_and_position_limit():
    values = config()
    values['goals'] = dict(hydropathy_min=-1, hydropathy_max=1)
    with pytest.raises(ValueError, match='point target'):
        compile_choices(ScalableChoiceRequest(**values))
    for parameters in ([[1]], [[float('nan'), 1]], [[1, 7]]):
        values = config()
        values['parameter_sets'] = parameters
        with pytest.raises((ValueError, ValidationError)):
            compile_choices(ScalableChoiceRequest(**values))
    with pytest.raises(ValidationError, match='10 variable'):
        ScalableChoiceRequest(**config('AK', 11))


def test_classical_search_exact_and_structured_large():
    request = ScalableChoiceRequest(**config())
    model = compile_choices(request)
    baseline = classical_search(model, request)
    assert baseline['exact_optimum_available']
    assert baseline['evaluations'] == 9
    assert baseline['best']['objective'] == pytest.approx(min(
        score_sequence(''.join(sequence), request)['objective'] for sequence in product('AKR', repeat=2)))
    request = ScalableChoiceRequest(**config('AGKR', 10))
    baseline = classical_search(compile_choices(request), request)
    assert not baseline['exact_optimum_available']
    assert baseline['best']['feasible'] and baseline['elapsed_seconds'] >= .1
    assert baseline['evaluations'] < 4**10


def test_invalid_samples_never_become_peptides():
    request = ScalableChoiceRequest(**config())
    model = compile_choices(request)
    result = summarize_counts(model, request, {'0011': 128})
    assert result['best_sampled'] is None and result['candidate_sequences'] == []
    assert result['invalid_shots'] == 128 and result['feasible_shots'] == 0


def test_real_mps_counts_and_full_local_result():
    request = ScalableChoiceRequest(**config())
    model = compile_choices(request)
    counts = sample_local(model, request, [1, .5], 8192, 42)
    expected = Statevector.from_instruction(build_circuit(model, [1, .5])).probabilities()
    measured = np.zeros(len(expected))
    for bits, count in counts.items():
        measured[int(bits, 2)] = count/8192
    np.testing.assert_allclose(measured, expected, atol=.025)
    result = run_scalable(request)
    assert result['provenance'] == 'simulated_approximate'
    assert result['summary']['shots'] == 128
    assert len(result['history']) == 10
    assert qasm2.loads(result['circuit']['qasm']).num_qubits == 4


def test_large_local_rejection_and_export_is_not_execution():
    request = ScalableChoiceRequest(**config(STANDARD_AMINO_ACIDS, 10))
    model = compile_choices(request)
    with pytest.raises(ValueError, match='budget'):
        sample_local(model, request, [1, .5], 128, 42)
    result = run_scalable(ScalableChoiceRequest(**config('AGKR', 3)), export_only=True)
    assert result['summary'] is None and result['provenance'] == 'prepared'
    assert result['quantum_workflow_seconds'] is None


def test_new_routes_and_disabled_hardware(monkeypatch):
    monkeypatch.delenv('PEPPERQ_ENABLE_QPU', raising=False)
    with TestClient(app) as client:
        response = client.post('/api/v1/sequence-design/scalable/preview', json=config())
        assert response.status_code == 200, response.text
        assert response.json()['qubits'] == 4
        hardware = client.post('/api/v1/sequence-design/scalable/qpu/prepare', json={'design': config(), 'backend_name': 'ibm_example'})
        assert hardware.status_code == 422 and 'disabled' in hardware.text
