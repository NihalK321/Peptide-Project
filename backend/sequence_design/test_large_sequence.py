"""Polynomial-space formulation and honest 50-qubit simulation/export contracts."""

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from qiskit import qasm2
from qiskit.quantum_info import Statevector

from backend.api import app
from .models import LargeSequenceRequest, SequenceDesignRequest
from .problem import score_sequence
from .scalable import compile_quadratic, decode, objective_value, scalable_circuit
from .large_solver import preview_large, run_large, sample_mps


def large_request(**changes):
    values = dict(length=50, allowed_amino_acids=["A", "K"], goals={"hydropathy_weight": 0}, shots=128)
    values.update(changes)
    return LargeSequenceRequest(**values)


def test_fifty_real_variables_without_enumeration():
    request = large_request()
    model = compile_quadratic(request)
    assert len(model["variables"]) == 50
    assert model["quadratic"].shape == (50, 50)
    assert "energies" not in model and "rows" not in model
    rng = np.random.default_rng(11)
    for _ in range(30):
        bits = rng.integers(0, 2, 50)
        row = score_sequence(decode(model["domains"], model["variables"], bits), request)
        assert objective_value(model, bits) == pytest.approx(row["objective"], abs=1e-8)
    assert preview_large(request)["state_count"] == 2 ** 50
    with pytest.raises(ValidationError, match="8 variable"):
        SequenceDesignRequest(length=50, allowed_amino_acids=["A", "K"])


@pytest.mark.parametrize("changes,message", [
    ({"required_amino_acids": ["K"]}, "fixed position"),
    ({"template_sequence": "A" * 50, "positions": [{"position": i+1,"choices":["A","K"]} for i in range(50)], "max_mutations": 2}, "mutation budget"),
    ({"goals": {"hydropathy_min": -1, "hydropathy_max": 1}}, "cost branches"),
])
def test_unsupported_terms_are_rejected_not_silently_removed(changes, message):
    with pytest.raises(ValueError, match=message):
        compile_quadratic(large_request(**changes))


@pytest.mark.parametrize("goals", [
    {"hydropathy_min": 0, "hydropathy_max": 0, "adjacent_repeat_weight": .5},
    {"hydropathy_min": -4.5, "hydropathy_max": 4.5},
    {"hydropathy_min": -4.5, "hydropathy_max": -4.5},
    {"hydropathy_min": 4.5, "hydropathy_max": 4.5},
])
def test_exact_analytic_cost_and_ising_on_every_small_assignment(goals):
    request = large_request(length=4, goals=goals)
    model = compile_quadratic(request)
    for index in range(16):
        bits = np.array([(index >> i) & 1 for i in range(4)])
        row = score_sequence(decode(model["domains"], model["variables"], bits), request)
        z = 1-2*bits
        assert objective_value(model, bits) == pytest.approx(row["objective"])
        assert model["offset"] + model["fields"] @ z + z @ model["couplings"] @ z == pytest.approx(row["objective"])


def test_fixed_required_and_nonbinding_budget_accepted():
    request = LargeSequenceRequest(length=4, template_sequence="KAAA", allowed_amino_acids=["A", "K"],
        positions=[{"position": i, "choices": ["A", "K"]} for i in (2, 3, 4)],
        required_amino_acids=["K"], max_mutations=3, goals={"hydropathy_weight": 0})
    assert len(compile_quadratic(request)["variables"]) == 3
    with pytest.raises(ValidationError, match="one QAOA layer"):
        large_request(layers=2)


def test_mps_matches_small_exact_distribution_with_sampling_tolerance():
    pytest.importorskip("qiskit_aer")
    model = compile_quadratic(large_request(length=4))
    parameters = [1.2, .4]
    ideal = Statevector.from_instruction(scalable_circuit(model, parameters)).probabilities()
    counts = sample_mps(model, parameters, 8192, 42, 16)
    observed = np.array([counts.get(format(i, '04b'), 0)/8192 for i in range(16)])
    np.testing.assert_allclose(observed, ideal, atol=.02, rtol=0)


def test_fifty_qubit_preparation_is_not_claimed_as_execution():
    result = run_large(large_request(), export_only=True)
    assert result["qubits"] == 50
    assert qasm2.loads(result["circuit"]["qasm"]).num_qubits == 50
    assert len(result["circuit"]["text"]) < 1000  # Full 50-qubit ASCII drawings can break browser storage.
    assert result["status"] == "circuit_prepared"
    assert result["counts"] == {} and result["shots"] == 0
    assert result["optimizer"] is None and result["best_sampled"] is None
    assert result["optimality_gap"] is None and not result["exact_optimum_available"]
    assert result["timings"]["qaoa_simulation_fit_and_sampling_seconds"] is None


def test_actual_fifty_qubit_mps_run():
    pytest.importorskip("qiskit_aer")
    result = run_large(large_request(mps_bond_dimension=8))
    assert result["qubits"] == 50
    assert result["execution_backend"] == "qiskit_aer_mps"
    assert result["provenance"] == "simulated_approximate"
    assert sum(result["counts"].values()) == 128
    assert all(len(bits) == 50 for bits in result["counts"])
    assert result["optimizer"]["evaluations"] == len(result["history"])
    assert result["simulator"]["certified_error_bound"] is None
    assert result["best_sampled"]["feasible"]
    assert result["sampled_minus_heuristic_objective"] == pytest.approx(result["best_sampled"]["objective"]-result["classical_baseline"]["objective"])
    assert result["timings"]["qaoa_simulation_fit_and_sampling_seconds"] > 0
    assert result["timings"]["classical_heuristic_seconds"] > 0


def test_large_api_does_not_replace_small_api():
    with TestClient(app) as client:
        data = large_request().model_dump()
        response = client.post("/api/v1/sequence-design/large/preview", json=data)
        assert response.status_code == 200
        assert response.json()["qubits"] == 50
        assert client.post("/api/v1/sequence-design/preview", json=data).status_code == 422
        assert client.post("/api/v1/sequence-design/large/preview", json={**data, "required_amino_acids": ["K"]}).status_code == 422
