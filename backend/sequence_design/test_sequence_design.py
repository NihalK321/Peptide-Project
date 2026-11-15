"""Sequence constraints, chemistry contract, exact mapping, and actual QAOA."""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from qiskit import QuantumCircuit, qasm2
from qiskit.circuit.library import DiagonalGate
from qiskit.quantum_info import Statevector

from backend.api import app
from .models import SequenceDesignRequest
from .problem import build_problem, chemical_properties, score_sequence
from .quantum import build_sequence_circuit
from .solver import optimize, preview


@pytest.fixture
def config():
    return {"length": 8, "template_sequence": "GAGAGAGA", "required_amino_acids": ["K"],
            "positions": [{"position": i, "choices": ["A", "K"]} for i in (2, 4, 6, 8)],
            "max_mutations": 2, "max_iterations": 15, "shots": 512}


def test_allowed_is_not_required_and_locked_positions_stay(config):
    request = SequenceDesignRequest(**config)
    problem = build_problem(request)
    assert len(problem["rows"]) == 16
    assert problem["feasible"].sum() == 10  # choose one or two K from four positions
    for index, row in enumerate(problem["rows"]):
        assert row["sequence"][::2] == "GGGG"
        assert row["sequence"][1] == ("K" if index & 1 else "A")
        assert ("K" in row["sequence"] and row["mutation_count"] <= 2) == row["feasible"]
    config["required_amino_acids"] = []
    rows = build_problem(SequenceDesignRequest(**config))["rows"]
    assert rows[0]["sequence"] == "GAGAGAGA" and rows[0]["feasible"]
    assert "R" in request.allowed_amino_acids and all("R" not in row["sequence"] for row in rows)


@pytest.mark.parametrize("change", [
    {"length": 1}, {"length": 51}, {"template_sequence": "GAZA"},
    {"positions": [{"position": 9, "choices": ["A"]}]},
    {"positions": [{"position": 1, "choices": ["A", "A"]}]},
    {"positions": [{"position": 1, "choices": ["A", "K", "G"]}]},
    {"positions": [{"position": 1, "choices": ["A"]}, {"position": 1, "choices": ["K"]}]},
    {"excluded_amino_acids": ["K"]}, {"required_amino_acids": ["R"]},
    {"allowed_amino_acids": ["A", "K"]},
    {"goals": {"ph": float("nan")}}, {"goals": {"ph": 15}},
    {"goals": {"hydropathy_min": 2, "hydropathy_max": 1}},
    {"goals": {"charge_weight": 0, "hydropathy_weight": 0}},
    {"shots": 0}, {"layers": 3}, {"max_mutations": 9},
])
def test_invalid_requests(config, change):
    config.update(change)
    with pytest.raises(ValidationError):
        SequenceDesignRequest(**config)


def test_design_from_length_and_implementation_cap():
    request = SequenceDesignRequest(length=3, allowed_amino_acids=["A", "K"], required_amino_acids=["K"])
    problem = build_problem(request)
    assert len(problem["rows"]) == 8
    assert problem["feasible"].sum() == 7
    with pytest.raises(ValidationError, match="8 variable"):
        SequenceDesignRequest(length=9, allowed_amino_acids=["A", "K"])
    with pytest.raises(ValidationError, match="template"):
        SequenceDesignRequest(length=3, allowed_amino_acids=["A", "K"], max_mutations=1)
    long_fixed = SequenceDesignRequest(length=50, template_sequence="A" * 50)
    assert preview(long_fixed)["state_count"] == 1
    with pytest.raises(ValueError, match="variable"):
        optimize(long_fixed)


def test_infeasible_requirements_budget_rejected(config):
    config["max_mutations"] = 0
    with pytest.raises(ValueError, match="No sequence"):
        build_problem(SequenceDesignRequest(**config))


def test_charge_and_range_components_and_order_preference(config):
    request = SequenceDesignRequest(**config)
    row = score_sequence("GKGKGAGA", request)
    q = chemical_properties(row["sequence"], 7.4)["charge"]
    assert row["objective"] == pytest.approx(((q-2)/2)**2 / 1.5)
    assert row["hydropathy_distance"] == 0
    # Same composition: no artificial claim that charge/GRAVY optimizes ordering.
    request = SequenceDesignRequest(length=4, template_sequence="AAKK", goals={"charge_weight": 0, "hydropathy_weight": 0, "adjacent_repeat_weight": 1})
    assert score_sequence("AAKK", request)["objective"] == pytest.approx(2/3)
    assert score_sequence("AKAK", request)["objective"] == 0
    assert chemical_properties("AAKK", 7.4)["hydropathy"] == pytest.approx(chemical_properties("AKAK", 7.4)["hydropathy"])


@pytest.mark.parametrize("higher_order", [False, True])
def test_exact_polynomial_and_circuit_match_all_states(config, higher_order):
    if not higher_order:
        config.update(required_amino_acids=[], max_mutations=None,
                      goals={"hydropathy_weight": 0, "adjacent_repeat_weight": .2})
    problem = build_problem(SequenceDesignRequest(**config))
    assert (problem["polynomial"]["representation"] == "higher_order_diagonal") == higher_order
    assert problem["polynomial"]["reconstruction_max_error"] < 1e-8
    for index, row in enumerate(problem["rows"]):
        assert problem["energies"][index] == pytest.approx(row["objective"] + problem["penalty"] * row["constraint_violation"])
    feasible = problem["feasible"]
    if (~feasible).any():
        assert problem["energies"][feasible].max() < problem["energies"][~feasible].min()
    parameters = [.71, .22, .41, .87]
    scale = max(np.ptp(problem["energies"]), 1e-12)
    expected = QuantumCircuit(4)
    expected.h(range(4))
    for gamma, beta in np.array(parameters).reshape(-1, 2):
        expected.append(DiagonalGate(np.exp(-1j * gamma * problem["energies"] / scale)), range(4))
        expected.rx(2 * beta, range(4))
    np.testing.assert_allclose(Statevector.from_instruction(build_sequence_circuit(problem, parameters)).probabilities(), Statevector.from_instruction(expected).probabilities(), atol=1e-10)


def test_actual_execution_decoding_gap_and_export(config):
    request = SequenceDesignRequest(**config)
    result = optimize(request)
    assert result["provenance"] == "simulated"
    assert result["optimizer"]["evaluations"] == len(result["history"])
    assert sum(row["count"] for row in result["states"]) == request.shots
    assert result["best_sampled"]["count"] > 0
    assert result["best_sampled"]["mutation_count"] <= 2
    assert "K" in result["best_sampled"]["sequence"]
    assert result["benchmark"]["sampled_objective_gap"] == pytest.approx(result["best_sampled"]["objective"] - result["classical_reference"]["objective"])
    assert result["classical_reference"]["objective"] == min(row["objective"] for row in result["states"] if row["feasible"])
    np.testing.assert_allclose(Statevector.from_instruction(qasm2.loads(result["circuit"]["qasm"])).probabilities(), [row["probability"] for row in result["states"]], atol=1e-10)
    assert optimize(request)["parameters"] == result["parameters"]


def test_no_feasible_sample_is_not_replaced(config, monkeypatch):
    def empty_only(problem, parameters):
        probabilities = np.zeros(len(problem["rows"]))
        probabilities[0] = 1
        return probabilities
    monkeypatch.setattr("backend.sequence_design.solver.sequence_probabilities", empty_only)
    result = optimize(SequenceDesignRequest(**config))
    assert result["best_sampled"] is None
    assert result["candidate_sequences"] == []
    assert result["status"] == "no_feasible_sample"
    assert result["classical_reference"]["feasible"]


def test_api_and_real_connectivity(config):
    with TestClient(app) as client:
        assert client.post("/api/v1/sequence-design/preview", json=config).json()["feasible_state_count"] == 10
        result = client.post("/api/v1/sequence-design/optimize", json=config)
        assert result.status_code == 200, result.text
        assert result.json()["benchmark"]["qubits"] == 4
        structure = client.post("/api/v1/sequence-design/structure", json={"sequence": "GAGA"})
        assert structure.status_code == 200
        assert '<svg' in structure.json()["svg"] and structure.json()["sequence"] == "GAGA"
        assert client.post("/api/v1/sequence-design/structure", json={"sequence": "AAZ"}).status_code == 422
        assert client.post("/api/v1/sequence-design/optimize", json={**config, "max_mutations": 0}).status_code == 422


def test_fifty_residues_eight_variables_all_256_states():
    request = SequenceDesignRequest(length=50, template_sequence="A" * 50,
        positions=[{"position": i + 1, "choices": ["A", "K"]} for i in range(8)],
        required_amino_acids=["K"], max_mutations=3)
    problem = build_problem(request)
    assert len(problem["variables"]) == 8
    assert len(problem["rows"]) == 256
    assert problem["feasible"].sum() == 92  # C(8,1)+C(8,2)+C(8,3)
    assert all(row["sequence"][8:] == "A" * 42 for row in problem["rows"])
    assert problem["polynomial"]["reconstruction_max_error"] < 1e-7
