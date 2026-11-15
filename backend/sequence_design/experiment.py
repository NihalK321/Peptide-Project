"""Save a real sequence QAOA run and circuit diagram for presentation/replay."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path

from .models import SequenceDesignRequest, LargeSequenceRequest
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
    parser.add_argument("--large", action="store_true", help="Analytical large-circuit model and bounded MPS simulation")
    parser.add_argument("--prepare-only", action="store_true", help="With --large, export an unoptimized starting circuit without execution")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; previous experiments are never overwritten.")
    if args.prepare_only and not args.large:
        parser.error("--prepare-only requires --large")
    if args.large:
        from .large_solver import run_large
        request = LargeSequenceRequest.model_validate_json(args.input.read_text(encoding="utf-8")) if args.input else LargeSequenceRequest(
            length=50, allowed_amino_acids=["A", "K"], goals={"hydropathy_min": 0, "hydropathy_max": 0}, shots=256)
        result = run_large(request, export_only=args.prepare_only)
        args.output.mkdir(parents=True)
        (args.output / "input.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")
        (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        (args.output / "circuit.qasm").write_text(result["circuit"]["qasm"], encoding="utf-8")
        (args.output / "circuit.txt").write_text(result["circuit"]["text"], encoding="utf-8")
        summary = {"qubits": result["qubits"], "status": result["status"], "execution_backend": result["execution_backend"],
                   "timings": result["timings"], "sampled_minus_heuristic_objective": result["sampled_minus_heuristic_objective"],
                   "exact_optimum_available": False, "shots": result["shots"]}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        print(f"Large-mode JSON and QASM/text artifacts: {args.output.resolve()}. No oversized PNG is generated.")
        return
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
