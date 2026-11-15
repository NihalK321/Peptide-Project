"""Reproducible 8-choose-3 experiment, verified exports, and a presentation summary.

Run from the repository root: python -m backend.blends.experiment
No network downloads, public API changes or quantum circuit rewrites occur.
"""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform

import numpy as np

from .catalog import BlendCatalog
from .models import BlendRequest, ShortlistRequest
from .quantum import build_blend_circuit
from .qubo import DescriptorExperiment, build_qubo
from .solver import optimize_blend, optimize_descriptor_input, shortlist
from .validation import verify_qubo


def analytical_fixture():
    """Synthetic mathematics only: descending scores, no pair penalty -> top 3."""
    candidates = [{"id": f"synthetic-{i}", "sequence": "A" + letter, "score": score}
                  for i, (letter, score) in enumerate(zip("ACDEFGHI", [1, .9, .8, .7, .6, .5, .4, .3]))]
    model = build_qubo(candidates, 3, 0)
    validation, subsets = verify_qubo(model, candidates, 3, 0)
    best = min(subsets, key=lambda row: row["objective"])
    if best["candidate_ids"] != ["synthetic-0", "synthetic-1", "synthetic-2"] or not np.isclose(best["objective"], -2.7):
        raise ValueError("Analytically solvable fixture failed.")
    return {"provenance": "synthetic_mathematical_fixture", "not_peptide_measurements": True,
            "expected_ids": ["synthetic-0", "synthetic-1", "synthetic-2"],
            "expected_objective": -2.7, "validation": validation, "actual_reference": best}


def export_result(result, output, input_snapshot):
    """Save the actual fitted circuit and JSON, refusing accidental overwrites."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    artifact_names = ["input.json", "result.json", "circuit.qasm", "circuit.png", "circuit.txt", "summary.md"]
    if any((output / name).exists() for name in artifact_names):
        raise ValueError("Experiment artifacts already exist; select a new --output directory.")
    result["software_versions"] = {name: version(name) for name in ("qiskit", "scipy", "numpy", "biopython")}
    result["software_versions"]["python"] = platform.python_version()
    result["analytical_fixture"] = analytical_fixture()
    circuit = build_blend_circuit(np.array(result["ising"]["fields"]),
        np.array(result["ising"]["couplings_upper_triangle"]), result["parameters"], result["circuit_metadata"]["energy_scale"])
    # Noninteractive renderer avoids Tk/GUI dependencies in a web or test thread.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure = circuit.draw(output="mpl", fold=32)
    figure.savefig(output / "circuit.png", dpi=160, bbox_inches="tight")
    plt.close(figure)
    (output / "circuit.txt").write_text(str(circuit.draw(output="text", fold=110)), encoding="utf-8")
    (output / "circuit.qasm").write_text(result["circuit_qasm"], encoding="utf-8")
    (output / "input.json").write_text(json.dumps(input_snapshot, indent=2, allow_nan=False), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    chosen = result["selected_blend"]
    reference = result["classical_reference"]
    summary = f"""# Verified peptide QUBO / QAOA experiment

Experiment: {result['experiment_id']}, {result['created_at']}

Execution: actual Qiskit ideal-statevector simulation, with seeded simulated shots.
This is not a hardware run. No quantum advantage or biological outcome is claimed.

- Candidate IDs in qubit order: {', '.join(result['candidate_ids'])}.
- Whole-peptide selection: exactly {result['goals']['blend_size']} of {len(result['candidates'])}.
- QAOA sampled selection: {chosen['candidate_ids'] if chosen else 'No feasible sample'}.
- Sampled bitstring (rightmost bit = candidate 0): {chosen['bitstring'] if chosen else 'Unavailable'}.
- QAOA sampled raw objective: {chosen['objective'] if chosen else 'Unavailable'}.
- Exact classical selection: {reference['candidate_ids']}.
- Exact classical raw objective: {reference['objective']}.
- Optimality gap: {result['benchmark']['sampled_objective_gap']}.
- Feasible shots: {result['sampling']['feasible_shots']} / {result['shots']}.
- Ideal probability of an optimum: {result['benchmark']['optimum_probability']}.
- COBYLA evaluations: {result['evaluations']}; converged: {result['converged']}.
- Exhaustive validation: {result['validation']}.

The best feasible observed sample is reported; an exact classical result is never
silently substituted. A zero observed gap does not mean guaranteed success on a
future shot, and a limited optimizer budget need not reach convergence.

`input.json` captures candidate sequences, descriptors, source URLs, and settings.
`result.json` contains the full upper-triangular QUBO, Ising offset/fields/couplings,
all 56 feasible subsets, actual fitting history, and feasible/infeasible counts.
`circuit.png` shows the actual fitted native circuit; `circuit.qasm` is its
equivalent expanded H/RZ/RX/CX representation for Composer.
"""
    (output / "summary.md").write_text(summary, encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="experiments/peptide_blend_verified")
    parser.add_argument("--input", type=Path, help="Optional DescriptorExperiment JSON; otherwise use the real local catalog")
    parser.add_argument("--candidate-ids", nargs=8, help="Eight exact catalog IDs; otherwise classically shortlist eight")
    args = parser.parse_args()
    if args.input and args.candidate_ids:
        parser.error("Choose --input or --candidate-ids, not both.")
    analytical_fixture()  # Verify simple known mathematics before real chemistry.
    if args.input:
        supplied = json.loads(args.input.read_text(encoding="utf-8"))
        experiment = DescriptorExperiment.model_validate(supplied.get("descriptor_replay", supplied))
        if len(experiment.candidates) != 8 or experiment.selection_count != 3:
            parser.error("The presentation experiment requires eight candidates and selection_count=3.")
        result = optimize_descriptor_input(experiment)
        snapshot = experiment.model_dump()
    else:
        catalog = BlendCatalog()
        pool = shortlist(catalog, ShortlistRequest())
        ids = args.candidate_ids or [candidate["id"] for candidate in pool["candidates"]]
        if len(ids) != 8:
            parser.error("Eight supported local peptides are required. Import a source catalog or provide --input; no fake data is substituted.")
        request = BlendRequest(candidate_ids=ids)
        result = optimize_blend(catalog, request)
        snapshot = {"catalog_request": request.model_dump(), "candidate_snapshot": result["candidates"],
                    "shortlist_method": pool["shortlist_method"] if args.candidate_ids is None else "Researcher-selected IDs",
                    "descriptor_replay": {"candidates": [{"id": row["id"], "name": row["name"], "sequence": row["sequence"],
                        "chemical_form": "linear_free_termini", "source": row["source"], "source_url": row["source_url"],
                        "descriptors": {**{key: row[key] for key in ("charge", "hydropathy", "mass_da", "ph")},
                                        "method": result["scoring_method"]["library"], "provenance": "calculated"}}
                        for row in result["candidates"]], "goals": {key: request.model_dump()[key] for key in ShortlistRequest.model_fields if key in ("ph", "target_charge", "target_hydropathy", "charge_weight", "hydropathy_weight", "diversity_weight")},
                        "selection_count": request.blend_size}}
    path = export_result(result, args.output, snapshot)
    print((path / "summary.md").read_text(encoding="utf-8"))
    print(f"Artifacts saved in: {path.resolve()}")


if __name__ == "__main__":
    main()
