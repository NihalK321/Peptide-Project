"""Input boundary, analytic fixture, bad outcomes, and reproducible artifacts."""

from copy import deepcopy
import json

import numpy as np
import pytest
from pydantic import ValidationError
from qiskit import qasm2
from qiskit.quantum_info import Statevector

from .experiment import analytical_fixture, export_result
from .models import BlendRequest
from .qubo import DescriptorExperiment, PairTerm, build_qubo
from .scoring import descriptors
from .solver import optimize_descriptor_input, solve_scored_candidates


@pytest.fixture
def descriptor_input():
    return {"candidates": [{"id": f"fixture-{i}", "name": f"Test peptide {i}",
        "sequence": sequence, "chemical_form": "linear_free_termini", "source": "test_fixture",
        "source_url": f"https://example.org/{i}",
        "descriptors": {**descriptors(sequence, 7.4), "ph": 7.4,
                        "method": "Biopython ProtParam, test sequences", "provenance": "calculated"}}
        for i, sequence in enumerate(["AAAA", "KKKK", "DDDD", "GAGA", "VILV", "STST", "RGDR", "YGGM"])]}


def test_analytic_eight_choose_three():
    result = analytical_fixture()
    assert result["actual_reference"]["bitstring"] == "00000111"
    assert result["actual_reference"]["objective"] == pytest.approx(-2.7)
    assert result["validation"]["checked_binary_states"] == 256
    assert result["validation"]["checked_feasible_subsets"] == 56


@pytest.mark.parametrize("mutation", [
    lambda value: value["candidates"][0]["descriptors"].pop("charge"),
    lambda value: value["candidates"][0]["descriptors"].update(charge=float("nan")),
    lambda value: value["candidates"][0]["descriptors"].update(hydropathy=5),
    lambda value: value["candidates"][0]["descriptors"].update(mass_da=-1),
    lambda value: value["candidates"][0]["descriptors"].update(charge=50),
    lambda value: value["candidates"][0]["descriptors"].update(ph=6),
    lambda value: value["candidates"][0]["descriptors"].update(provenance="invented"),
    lambda value: value["candidates"][0].update(sequence="AAXA"),
    lambda value: value["candidates"][0].update(chemical_form="cyclic"),
    lambda value: value["candidates"][0].update(modifications=["amidation"]),
    lambda value: value["candidates"][0].update(id="fixture-1"),
    lambda value: value.update(selection_count=8),
    lambda value: value.update(pair_terms=[]),
])
def test_missing_invalid_and_unsupported_descriptors_rejected(descriptor_input, mutation):
    mutation(descriptor_input)
    with pytest.raises(ValidationError):
        DescriptorExperiment.model_validate(descriptor_input)


def explicit_pairs(ids):
    return [{"first_id": first, "second_id": second, "penalty": .25,
             "method": "researcher_supplied_redundancy"}
            for i, first in enumerate(ids) for second in ids[i + 1:]]


def test_upper_triangle_and_explicit_pair_accounting(descriptor_input):
    experiment = DescriptorExperiment.model_validate(descriptor_input)
    candidates = experiment.scored_candidates()
    terms = [PairTerm.model_validate(row) for row in explicit_pairs([candidate["id"] for candidate in candidates])]
    model = build_qubo(candidates, 3, .8, terms)
    expected_penalty = sum(candidate["score"] for candidate in candidates) + .8 * 28 * .25 + 1
    assert model["penalty"] == pytest.approx(expected_penalty)
    assert model["matrix_upper_triangle"][0, 0] == pytest.approx(-candidates[0]["score"] - 5 * expected_penalty)
    assert model["matrix_upper_triangle"][0, 1] == pytest.approx(.8 * .25 + 2 * expected_penalty)
    assert model["matrix_upper_triangle"][1, 0] == 0
    assert model["raw_cost"][7] == pytest.approx(-sum(row["score"] for row in candidates[:3]) + .8 * .25 * 3)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "self", "unknown", "negative", "false_method"])
def test_bad_pair_contract_rejected(descriptor_input, kind):
    terms = explicit_pairs([candidate["id"] for candidate in descriptor_input["candidates"]])
    if kind == "missing":
        terms.pop()
    elif kind == "duplicate":
        duplicate = deepcopy(terms[0])
        duplicate["first_id"], duplicate["second_id"] = duplicate["second_id"], duplicate["first_id"]
        terms.append(duplicate)
    elif kind == "self":
        terms[0]["second_id"] = terms[0]["first_id"]
    elif kind == "unknown":
        terms[0]["first_id"] = "missing-id"
    elif kind == "negative":
        terms[0]["penalty"] = -1
    else:
        terms[0]["method"] = "sequence_bigram_jaccard"
    descriptor_input["pair_terms"] = terms
    with pytest.raises(ValidationError):
        DescriptorExperiment.model_validate(descriptor_input)


@pytest.mark.parametrize("score", [None, float("nan"), -0.1, 1.1])
def test_bad_normalized_mathematical_score_rejected(score):
    with pytest.raises(ValidationError):
        build_qubo([{"id": "a", "sequence": "AA", "score": score},
                    {"id": "b", "sequence": "KK", "score": .5}], 1, .3)


def test_worse_qaoa_result_is_not_presented_as_optimal(monkeypatch):
    candidates = [{"id": f"math-{i}", "sequence": "A" + letter, "score": score}
        for i, (letter, score) in enumerate(zip("ACDEFGHI", [1, .9, .8, .7, .6, .5, .4, .3]))]
    # Force the observed circuit distribution to select the three LOWEST scores.
    # This mocked test is not reported as an actual quantum experiment.
    distribution = np.zeros(256)
    distribution[0b11100000] = 1
    monkeypatch.setattr("backend.blends.solver.probabilities", lambda *args: distribution.copy())
    request = BlendRequest(candidate_ids=[row["id"] for row in candidates], diversity_weight=0, max_iterations=10)
    result = solve_scored_candidates(candidates, request, {"source": "synthetic mathematical test"})
    assert result["selected_blend"]["candidate_ids"] == ["math-5", "math-6", "math-7"]
    assert result["selected_blend"]["objective"] == pytest.approx(-1.2)
    assert result["classical_reference"]["objective"] == pytest.approx(-2.7)
    assert result["benchmark"]["sampled_objective_gap"] == pytest.approx(1.5)
    assert result["benchmark"]["optimum_probability"] == 0


def test_descriptor_pipeline_and_verified_exports(descriptor_input, tmp_path):
    descriptor_input["max_iterations"] = 10
    descriptor_input["pair_terms"] = explicit_pairs([candidate["id"] for candidate in descriptor_input["candidates"]])
    experiment = DescriptorExperiment.model_validate(descriptor_input)
    result = optimize_descriptor_input(experiment)
    assert result["candidate_ids"] == [candidate["id"] for candidate in descriptor_input["candidates"]]
    assert result["validation"]["passed"]
    assert len(result["classical_feasible_selections"]) == 56
    assert result["catalog"]["descriptors_independently_verified"] is False
    assert result["selected_blend"]["objective"] >= result["classical_reference"]["objective"] - 1e-10
    sampling = result["sampling"]
    assert sampling["feasible_shots"] + sampling["infeasible_shots"] == result["shots"]
    assert all(bits.count("1") == 3 for bits in sampling["feasible_counts"])
    assert all(bits.count("1") != 3 for bits in sampling["infeasible_counts"])
    assert {**sampling["feasible_counts"], **sampling["infeasible_counts"]} == result["counts"]
    output = export_result(result, tmp_path, descriptor_input)
    assert (output / "circuit.png").read_bytes().startswith(b"\x89PNG")
    exported = qasm2.loads((output / "circuit.qasm").read_text())
    np.testing.assert_allclose(Statevector.from_instruction(exported).probabilities(), list(result["probabilities"].values()), atol=1e-12)
    saved = json.loads((output / "result.json").read_text())
    assert saved["experiment_id"] == result["experiment_id"]
    assert saved["analytical_fixture"]["validation"]["passed"]
    assert DescriptorExperiment.model_validate_json((output / "input.json").read_text()).request() == experiment.request()
    with pytest.raises(ValueError, match="already exist"):
        export_result(result, tmp_path, descriptor_input)
