"""Compact multi-residue encoding, penalties, actual QAOA, and API isolation."""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from qiskit import qasm2
from qiskit.quantum_info import Statevector

from backend.api import app
from backend.schema import STANDARD_AMINO_ACIDS
from .models import MultiChoiceRequest, SequenceDesignRequest
from .problem import build_problem, score_sequence
from .quantum import build_sequence_circuit, sequence_probabilities
from .solver import optimize, preview


def config(choices=None):
    choices = list(STANDARD_AMINO_ACIDS) if choices is None else choices
    return dict(length=4, template_sequence="GAGA", max_mutations=2,
                positions=[dict(position=i, choices=choices) for i in (2, 4)],
                max_iterations=10, shots=512, seed=42)


def test_twenty_choices_two_positions_and_little_endian_decoding():
    request = MultiChoiceRequest(**config())
    problem = build_problem(request)
    report = preview(request)
    assert report["qubits"] == 10
    assert report["state_count"] == 1024
    assert report["feasible_state_count"] == 400
    assert report["encoding"]["invalid_code_count"] == 624
    rows = problem["rows"]
    assert rows[1]["sequence"] == "GCGA"
    assert rows[32]["sequence"] == "GAGC"
    assert rows[19 + (19 << 5)]["sequence"] == "GYGY"
    assert rows[20]["sequence"] is None
    assert not rows[20]["valid_encoding"]
    assert len({row["sequence"] for row in rows if row["valid_encoding"]}) == 400
    for row in rows:
        if row["valid_encoding"]:
            assert row["sequence"][::2] == "GG"
            assert row["objective"] == score_sequence(row["sequence"], request)["objective"]
    feasible = problem["feasible"]
    assert problem["energies"][~feasible].min() > problem["energies"][feasible].max()
    assert problem["polynomial"]["reconstruction_max_error"] < 1e-6


def test_constraints_and_non_power_of_two_alphabets():
    values = config(["A", "K", "R"])
    values.update(required_amino_acids=["K"], max_mutations=1)
    problem = build_problem(MultiChoiceRequest(**values))
    assert len(problem["rows"]) == 16
    assert sum(row["valid_encoding"] for row in problem["rows"]) == 9
    assert problem["feasible"].sum() == 2
    for row in problem["rows"]:
        if row["feasible"]:
            assert "K" in row["sequence"] and row["mutation_count"] == 1


@pytest.mark.parametrize("change", [
    {"positions": [dict(position=i, choices=["A", "K", "G"]) for i in (1, 2, 3)]},
    {"positions": [dict(position=2, choices=["A", "A", "K"])]},
    {"positions": [dict(position=2, choices=["A", "Z", "K"])]},
    {"excluded_amino_acids": ["K"]},
    {"positions": [dict(position=5, choices=["A", "K"])]},
])
def test_invalid_multi_requests(change):
    values = config()
    values.update(change)
    with pytest.raises(ValidationError):
        MultiChoiceRequest(**values)


def test_old_binary_mode_still_rejects_twenty_choices():
    with pytest.raises(ValidationError):
        SequenceDesignRequest(**config())


def test_fast_amplitude_execution_equals_exported_circuit():
    problem = build_problem(MultiChoiceRequest(**config(["A", "K", "R"])))
    parameters = [.7, .4, 1.3, -.2]
    circuit = build_sequence_circuit(problem, parameters)
    np.testing.assert_allclose(sequence_probabilities(problem, parameters),
                               Statevector.from_instruction(circuit).probabilities(), atol=1e-12)


def test_actual_ten_qubit_run_counts_and_exact_reference():
    result = optimize(MultiChoiceRequest(**config()))
    assert result["benchmark"]["qubits"] == 10
    assert sum(row["count"] for row in result["states"]) == 512
    assert sum(row["probability"] for row in result["states"]) == pytest.approx(1)
    feasible = [row for row in result["states"] if row["feasible"]]
    optimum = min(row["objective"] for row in feasible)
    assert result["classical_reference"]["objective"] == optimum
    assert result["benchmark"]["feasible_probability"] == pytest.approx(sum(row["probability"] for row in feasible))
    assert result["benchmark"]["optimum_probability"] == pytest.approx(sum(
        row["probability"] for row in feasible if np.isclose(row["objective"], optimum, atol=1e-8, rtol=0)))
    assert all(row["valid_encoding"] and row["count"] > 0 for row in result["candidate_sequences"])
    assert result["best_sampled"]["objective"] - optimum == result["benchmark"]["sampled_objective_gap"]
    assert qasm2.loads(result["circuit"]["qasm"]).num_qubits == 10
    assert len(result["circuit"]["text"]) < 1000


def test_no_feasible_sample_does_not_insert_classical_answer(monkeypatch):
    # All probability on code 3, invalid for a three-choice first position.
    def invalid_only(problem, parameters):
        probabilities = np.zeros(len(problem["rows"]))
        probabilities[3] = 1
        return probabilities
    monkeypatch.setattr("backend.sequence_design.solver.sequence_probabilities", invalid_only)
    result = optimize(MultiChoiceRequest(**config(["A", "K", "R"])))
    assert result["best_sampled"] is None
    assert result["candidate_sequences"] == []
    assert result["status"] == "no_feasible_sample"
    assert result["benchmark"]["infeasible_shots"] == 512


def test_multi_routes_and_binary_route_are_separate():
    with TestClient(app) as client:
        response = client.post("/api/v1/sequence-design/multi/preview", json=config())
        assert response.status_code == 200, response.text
        assert response.json()["encoding"]["valid_sequence_count"] == 400
        assert client.post("/api/v1/sequence-design/preview", json=config()).status_code == 422
        result = client.post("/api/v1/sequence-design/multi/optimize", json=config(["A", "K", "R"]))
        assert result.status_code == 200, result.text
        assert result.json()["execution_backend"] == "qiskit_statevector"
