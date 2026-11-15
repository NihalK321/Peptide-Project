"""Save a real sequence QAOA run and circuit diagram for presentation/replay."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path

from .models import SequenceDesignRequest
from .problem import build_problem
from .quantum import build_sequence_circuit
from .solver import optimize


def demonstration_request():
    return SequenceDesignRequest(length=8, template_sequence="GAGAGAGA",
        positions=[{"position": i, "choices": ["A", "K"]} for i in (2, 4, 6, 8)],
        required_amino_acids=["K"], max_mutations=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Optional SequenceDesignRequest JSON")
    parser.add_argument("--output", type=Path, default=Path("experiments/sequence_design_verified"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; previous experiments are never overwritten.")
    request = SequenceDesignRequest.model_validate_json(args.input.read_text(encoding="utf-8")) if args.input else demonstration_request()
    result = optimize(request)
    result["software_versions"] = {name: version(name) for name in ("qiskit", "numpy", "scipy", "biopython")}
    circuit = build_sequence_circuit(build_problem(request), result["parameters"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure = circuit.draw(output="mpl", fold=28)
    args.output.mkdir(parents=True)
    figure.savefig(args.output / "circuit.png", dpi=160, bbox_inches="tight")
    plt.close(figure)
    (args.output / "input.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")
    (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    (args.output / "circuit.qasm").write_text(result["circuit"]["qasm"], encoding="utf-8")
    (args.output / "circuit.txt").write_text(result["circuit"]["text"], encoding="utf-8")
    best = result["best_sampled"]
    reference = result["classical_reference"]
    summary = f"""# Actual restricted sequence-design experiment

Qiskit ideal-statevector simulation; shot counts are simulated, not hardware.
Illustrative template, not a therapeutic reference: {request.template_sequence}
Variable-position mapping: {result['variables']}
Research goals: {request.goals.model_dump()}
Required residues: {request.required_amino_acids}; maximum changes: {request.max_mutations}

Best feasible observed sequence: {best['sequence'] if best else 'None observed'}
Observed raw objective: {best['objective'] if best else 'Unavailable'}
Exact classical reference: {reference['sequence']}; raw objective {reference['objective']}
Sampled objective gap: {result['benchmark']['sampled_objective_gap']}
Feasible simulated shots: {result['benchmark']['feasible_shots']}/{request.shots}
Ideal probability of an optimum: {result['benchmark']['optimum_probability']}
Tied exact optima: {result['benchmark']['optimal_sequences_count']}
Optimizer converged: {result['optimizer']['converged']}; {result['optimizer']['evaluations']} evaluations
Cost representation: {result['cost']['representation']}; polynomial degree {result['cost']['degree']}
Validation: {result['validation']}

The exact answer is never substituted as a quantum result. Matching its score
does not establish guaranteed success, biological efficacy or quantum advantage.
All cost states were enumerated classically for this bounded experiment.
"""
    (args.output / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"Artifacts: {args.output.resolve()}")


if __name__ == "__main__":
    main()
